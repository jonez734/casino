# casino/auth.py
# BED-server authentication and BBS module entry points.
#
# Override hooks:
#   - auth.auth_prompt (module-level): swap the entire auth prompt
#   - CasinoClient.auth_prompt (class-level): per-subclass carve-out
#
# Both resolve to the same D-shape callable:
#   async def auth_prompt(args: argparse.Namespace, client: CasinoClient) -> bool
# The prompt owns the client.send(...) call and returns True to continue,
# False to abort.
#
# Bearer-token auth: when ``args.token_file`` is set and points at a
# non-empty file, :func:`connect` uses
# :class:`bed.client.authservice.BedAuthServiceClient.reconnect` to
# bind an existing token to the freshly-opened WebSocket. This is
# the same flow ``bed tools bank`` uses and is the supported path
# for headless / scripted casino clients (CI, bots, automation).
# The legacy prompt-based path stays in place for interactive
# sessions.

from __future__ import annotations

import argparse
import asyncio
from typing import TYPE_CHECKING

from bbsengine6 import bottombar, io, util

from .client.registry import _clients, _current_moniker

if TYPE_CHECKING:
    from .client.casino_client import CasinoClient


# ---- Auth prompt: the single override point --------------------------

async def auth_prompt(args: argparse.Namespace, client: CasinoClient) -> bool:
    """Default BED auth prompt.

    Prompts for moniker and (if the member has one) a password, then sends
    the auth message through `client`. Override this — or assign a new
    callable to `auth.auth_prompt`, or set `CasinoClient.auth_prompt` on a
    subclass — to customize the credential flow.

    Returns:
        True if the prompt completed (whether or not the server accepted),
        False to abort the connect flow.
    """
    moniker = io.inputstring("{var:promptcolor}Moniker: {var:inputcolor}", None, None)
    if not moniker:
        return False
    # The remote client does not have a local database, so it cannot know
    # whether a member requires a password. Always prompt and let the server
    # decide. (member.has_password needs DB args the client does not carry.)
    password = util.inputpassword("Password: ")
    await client.send({"type": "auth", "moniker": moniker, "password": password})
    return True


# ---- BBS module entry points -----------------------------------------

def init(args, **kwargs) -> bool:
    return True


def access(args, op: str, **kwargs) -> bool:
    return True


def buildargs(args, **kwargs):
    """Register casino-specific CLI flags.

    Adds ``--token-file`` so :func:`connect` can pick up an existing
    bed bearer token (the same path used by ``bed tools bank``). The
    flag mirrors :func:`bed.tools._token.build_token_file_arg` so the
    default path (``$XDG_RUNTIME_DIR/bed.token`` or
    ``/tmp/bed-<uid>/bed.token``) and permission checks are shared.
    """
    from bed.tools import _token

    parser = args._parser if hasattr(args, "_parser") else None
    if parser is not None:
        try:
            _token.build_token_file_arg(parser)
        except Exception:
            pass
    if not hasattr(args, "token_file"):
        args.token_file = None
    return None


def _casino_table_fragment(**kwargs) -> str:
    from .client import get_client
    c = get_client()
    if c is None or c.current_table_moniker is None:
        return ""
    return f"{c.current_table_moniker} ({c.current_table_game_type}) players: {c.current_table_players}"


def init_remote_client_screen() -> None:
    from bbsengine6 import io as bbsio

    bbsio.screen.init()
    bottombar.register_bottombar_fragment(_casino_table_fragment)


def cleanup_remote_client_screen() -> None:
    bottombar.unregister_bottombar_fragment(_casino_table_fragment)


def _read_token_file(path: str) -> str:
    """Read a bearer token from ``path``.

    Returns the first non-empty stripped line, or ``""`` when the
    file is missing, empty, or unreadable. Mirrors the behaviour of
    ``bed.tools._token.read_token_file`` without taking a hard
    dependency on the helper so this module remains importable in
    door-mode contexts where bed is not on the path.
    """
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                tok = line.strip()
                if tok and not tok.startswith("#"):
                    return tok
    except OSError:
        return ""
    return ""


def _open_loop_for(client) -> asyncio.AbstractEventLoop:
    """Create and bind a fresh event loop to ``client`` if it doesn't
    already have one. Returns the loop. This lets callers inject a
    pre-built client (e.g. tests with a stubbed loop) without the
    connect path clobbering it.
    """
    if getattr(client, "_loop", None) is None:
        client._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(client._loop)
    return client._loop


def _connect_with_token(args, host: str, port: int) -> CasinoClient | None:
    """Connect and bind an existing bearer token via ``auth reconnect``.

    Mirrors ``bed.tools.bank._authenticate_ws`` minus the token
    rotation logic. The returned client has ``authenticated=True``
    and the resolved token stashed on ``client._bearer_token`` so
    per-op sends can inject it on every wire call.
    """
    from bed.client import get_bed_connection
    from bed.client.authservice import BedAuthServiceClient

    from .client import CasinoClient

    token_path = getattr(args, "token_file", None) or ""
    token = _read_token_file(token_path) if token_path else ""
    if not token:
        io.echo(
            f"no bearer token found at {token_path}; run "
            f"'bed auth login' first or pass --token-file <path>",
            level="error",
        )
        return None

    client = CasinoClient(args)
    _open_loop_for(client)

    if not client._loop.run_until_complete(client.connect()):
        client._loop.close()
        io.echo("Failed to connect", level="error")
        return None

    bed_conn = get_bed_connection(args)
    bed_conn._ws = client.ws  # share the open socket
    auth_client = BedAuthServiceClient(bed_conn)
    try:
        reply = client._loop.run_until_complete(auth_client.reconnect(token))
    finally:
        # After reconnect the bed_conn owns the WS; the casino
        # client continues to use it through its own reference.
        bed_conn._ws = client.ws

    if not reply.get("ok"):
        code = reply.get("code") or "unknown"
        message = reply.get("message") or ""
        if code in (
            "not_authenticated",
            "token_invalid",
            "token_revoked",
            "token_expired",
            "bed_instance_mismatch",
        ):
            io.echo(
                f"token at {token_path} rejected by server "
                f"({code}: {message}); run 'bed auth login' again",
                level="error",
            )
        else:
            io.echo(f"{code}: {message}".rstrip(), level="error")
        client._loop.run_until_complete(client.disconnect())
        client._loop.close()
        return None

    client.authenticated = True
    client.moniker = reply.get("moniker", "") or ""
    client.is_sysop = bool(reply.get("is_sysop", False))
    client.balance = int(reply.get("balance", 0) or 0)
    client._bearer_token = reply.get("token") or token
    client._receive_task = client._loop.create_task(client.receive_loop())
    return client


def connect(args, **kwargs) -> CasinoClient | None:
    """BBS entry point: connect to the BED server and run the auth prompt.

    When ``args.token_file`` is set and points at a non-empty token
    file, this uses the bearer-token ``auth reconnect`` flow
    (:func:`_connect_with_token`) instead of the legacy
    ``auth_prompt`` flow. The token-bearing path mirrors what
    ``bed tools bank`` does so headless / scripted casino clients
    can drive the same WS without an interactive prompt.
    """
    from .client import CasinoClient

    util.heading("connect to server")
    host = getattr(args, "bed_host", "127.0.0.1")
    port = int(getattr(args, "bed_port", 8765))
    io.echo(f"Connecting to {host}:{port}...")

    token_path = getattr(args, "token_file", None) or ""
    if token_path:
        client = _connect_with_token(args, host, port)
    else:
        client = CasinoClient(args)
        _open_loop_for(client)

        if not client._loop.run_until_complete(client.connect()):
            client._loop.close()
            io.echo("Failed to connect", level="error")
            return None

        client._receive_task = client._loop.create_task(client.receive_loop())

        if not client._loop.run_until_complete(auth_prompt(args, client)):
            client._loop.run_until_complete(client.disconnect())
            client._loop.close()
            io.echo("Auth aborted", level="error")
            return None

        client._loop.run_until_complete(asyncio.sleep(0.5))

        if not client.authenticated:
            client._loop.run_until_complete(client.disconnect())
            client._loop.close()
            io.echo("Authentication failed", level="error")
            return None

    if client is None:
        return None

    _clients[client.moniker] = client
    _current_moniker = client.moniker
    io.echo(f"Connected as {client.moniker}, balance: {client.balance}")
    return client


def disconnect(args, client: CasinoClient | None = None, **kwargs) -> bool:
    global _current_moniker
    from .client import get_client
    client = client or get_client()
    if client is None:
        io.echo("Not connected.", level="error")
        return False
    client._loop.run_until_complete(client.disconnect())
    client._loop.close()
    if client.moniker in _clients:
        del _clients[client.moniker]
    if _current_moniker == client.moniker:
        _current_moniker = None
    io.echo("Disconnected.")
    return True


def main(args, **kwargs) -> bool:
    return connect(args, **kwargs)
