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

from __future__ import annotations

import argparse
import asyncio
from typing import TYPE_CHECKING

from bbsengine6 import io, member, util, bottombar

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
    password = ""
    if member.has_password(args, moniker):
        password = util.inputpassword("Password: ")
    await client.send({"type": "auth", "moniker": moniker, "password": password})
    return True


# ---- BBS module entry points -----------------------------------------

def init(args, **kwargs) -> bool:
    return True


def access(args, op: str, **kwargs) -> bool:
    return True


def buildargs(args, **kwargs):
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


def connect(args, **kwargs) -> CasinoClient | None:
    """BBS entry point: connect to the BED server and run the auth prompt."""
    from .client import CasinoClient

    util.heading("connect to server")
    host = getattr(args, "host", "127.0.0.1")
    port = getattr(args, "port", 8765)
    io.echo(f"Connecting to {host}:{port}...")

    client = CasinoClient(args)
    client._loop = asyncio.new_event_loop()
    asyncio.set_event_loop(client._loop)

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
