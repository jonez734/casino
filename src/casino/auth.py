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
import contextlib
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


def buildargs(args, parser: argparse.ArgumentParser | None = None, **kwargs):
    """Register casino-specific CLI flags.

    Adds ``--token-file`` so :func:`connect` and :func:`CasinoClient.run`
    can pick up an existing bed bearer token (the same path used by
    ``bed tools bank``). The flag mirrors
    :func:`bed.tools._token.build_token_file_arg` so the default path
    (``$XDG_RUNTIME_DIR/bed.token`` or ``/tmp/bed-<uid>/bed.token``) and
    permission checks are shared.

    Two call shapes:

    - ``buildargs(args, parser=parser)`` from the merged ``casino``
      CLI's parser-build path (``casino.lib.buildargs``). The parser
      is required so the flag lands on the merged CLI's argparse.
    - ``buildargs(args)`` from the BBS-dispatch path
      (``bbsengine6.module.runmodule`` → ``casino.lib.buildargs``).
      No parser is available; the function only ensures
      ``args.token_file`` defaults to ``None``.
    """
    if parser is not None:
        from bed.tools import _token
        _token.build_token_file_arg(parser)
    if args is not None and not hasattr(args, "token_file"):
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


def _resolve_token_file(args) -> None:
    """Resolve ``args.token_file`` to a usable state.

    Mutates ``args`` in place:

    1. If ``args.token_file`` is unset, fill it with the default
       ``$XDG_RUNTIME_DIR/bed.token`` (or ``/tmp/bed-<uid>/bed.token``)
       via :func:`bed.tools._token.ensure_token_file_arg`.
    2. If ``args.token_file`` is set but the file is empty (or
       missing), clear it back to ``None`` so downstream
       ``if args.token_file:`` checks cleanly fall through to the
       prompt path. This is the silent-fallback that lets an
       operator run ``casino`` without a token file (e.g. before
       they have run ``bed auth login``) and still get the prompt.
    """
    from bed.tools import _token

    _token.ensure_token_file_arg(args)
    if args.token_file and not _read_token_file(args.token_file):
        args.token_file = None


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


def _close_loop_for(
    client,
    loop: asyncio.AbstractEventLoop | None = None,
) -> None:
    """Close ``client._loop`` (or ``loop``), letting pending tasks
    finish gracefully first.

    Mirrors the shutdown sequence ``asyncio.run()`` uses in CPython
    3.12: identify every task still owned by the loop, request
    cancellation on each, then await them so the ``CancelledError``
    propagates through each coroutine (closing sockets, flushing
    buffers, etc.). Then shut down async generators and the default
    executor, and finally close the loop. Everything runs inside a
    ``finally`` block so the loop is always closed, even if a task's
    cancellation handler itself raises.

    Without the cancel-then-await drain, websockets' internal
    ``Connection.keepalive`` task (and anything else the loop owns
    that's still pending) is left in pending state when
    ``loop.close()`` runs, and Python prints ``RuntimeWarning: Task
    was destroyed but it is pending!`` at interpreter shutdown.

    Args:
        client: an object carrying ``_loop`` (e.g. a ``CasinoClient``).
            Ignored when ``loop`` is passed directly.
        loop: the loop to close. When ``None``, falls back to
            ``client._loop``. When neither resolves, the function is
            a no-op so call sites don't have to guard against a
            missing loop.
    """
    target = loop if loop is not None else getattr(client, "_loop", None)
    if target is None:
        return
    try:
        pending = [t for t in asyncio.all_tasks(target) if not t.done()]
        for t in pending:
            t.cancel()
        if pending:
            target.run_until_complete(
                asyncio.gather(*pending, return_exceptions=True)
            )
        target.run_until_complete(target.shutdown_asyncgens())
        target.run_until_complete(target.shutdown_default_executor())
    finally:
        target.close()


def _connect_with_token(
    args,
    host: str,
    port: int,
    client: CasinoClient | None = None,
) -> CasinoClient | None:
    """Connect and bind an existing bearer token via ``auth reconnect``.

    Mirrors ``bed.tools.bank._authenticate_ws`` minus the token
    rotation logic. The returned client has ``authenticated=True``
    and the resolved token stashed on ``client._bearer_token`` so
    per-op sends can inject it on every wire call.

    ``client``: when ``None`` (default, the BBS-dispatch path used by
    :func:`connect`), a fresh :class:`CasinoClient` is constructed
    from ``args`` and returned. When supplied
    (e.g. by :meth:`CasinoClient.run` on the merged CLI's BED-mode
    path), ``client`` is mutated in place: the loop is opened, the
    WebSocket is opened, ``BedAuthServiceClient.reconnect(token)`` is
    driven against the shared ``bed.client.get_bed_connection`` WS,
    and the resolved state (``authenticated``, ``moniker``,
    ``is_sysop``, ``balance``, ``_bearer_token``, ``_receive_task``)
    is set on ``client``. Returns ``None`` on failure in either shape.
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

    if client is None:
        client = CasinoClient(args)

    _open_loop_for(client)

    if not client._loop.run_until_complete(client.connect()):
        _close_loop_for(client)
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
            # Diagnostic: when an operator hits the ``token_revoked``
            # wall right after ``bed auth login``, this line confirms
            # the token file under the operator's nose is the file
            # that was just read (token prefix + mtime) so we can
            # tell "stale file" from "right file, server lost it"
            # without asking the operator for the raw token. Bed
            # tags its AuthService logs with the same 8-char prefix
            # via :func:`bed.api.auth._token_hash` so a single
            # ``grep tok=<prefix>`` correlates client and server
            # frames. Unconditional -- operator log surface, not
            # debug-only.
            try:
                import hashlib as _hl
                import os as _os
                import time as _time
                st = _os.stat(token_path)
                io.echo(
                    f"casino_reject.debug: token_file={token_path} "
                    f"mtime={_time.strftime('%Y-%m-%dT%H:%M:%S', _time.gmtime(st.st_mtime))}Z "
                    f"size={st.st_size} "
                    f"token_sha256_prefix={_hl.sha256(token.encode('utf-8')).hexdigest()[:8]}",
                )
            except OSError as e:
                io.echo(f"casino_reject.debug: stat failed: {e}")
        else:
            io.echo(f"{code}: {message}".rstrip(), level="error")
        client._loop.run_until_complete(client.disconnect())
        _close_loop_for(client)
        return None

    client.authenticated = True
    client.moniker = reply.get("moniker", "") or ""
    client.balance = int(reply.get("balance", 0) or 0)
    is_sysop = bool(reply.get("is_sysop", False))
    if not hasattr(client, "is_sysop"):
        with contextlib.suppress(AttributeError, TypeError):
            client.is_sysop = is_sysop
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
            _close_loop_for(client)
            io.echo("Failed to connect", level="error")
            return None

        client._receive_task = client._loop.create_task(client.receive_loop())

        if not client._loop.run_until_complete(auth_prompt(args, client)):
            client._loop.run_until_complete(client.disconnect())
            _close_loop_for(client)
            io.echo("Auth aborted", level="error")
            return None

        client._loop.run_until_complete(asyncio.sleep(0.5))

        if not client.authenticated:
            client._loop.run_until_complete(client.disconnect())
            _close_loop_for(client)
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
    _close_loop_for(client)
    if client.moniker in _clients:
        del _clients[client.moniker]
    if _current_moniker == client.moniker:
        _current_moniker = None
    io.echo("Disconnected.")
    return True


def main(args, **kwargs) -> bool:
    return connect(args, **kwargs)
