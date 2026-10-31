# commands/chat/lib.py
# Chat command functions

import asyncio

from bbsengine6 import io
from casino import host

# Shared helpers live in commands/_common.py. The underscore names are kept so
# existing callers and tests keep working.
from casino.commands._common import get_client as get_client  # noqa: E402


def chat(args, client=None, **kwargs) -> bool:
    """Send global chat message."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    client.cmd_chat()
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def table_chat(args, client=None, **kwargs) -> bool:
    """Send table chat message."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    if getattr(client, "current_table_moniker", None) is None:
        io.echo("Not at a table.", level="error")
        return False
    client.cmd_table_chat()
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def menu(args, client=None, **kwargs):
    """Show chat operations submenu."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False

    while True:
        cmd = (host.choose("{var:promptcolor}[G]lobal  [T]able  [Q]uit: {var:inputcolor}", "g,t,q", default="q") or "").upper()

        if cmd == "G":
            chat(args, client=client, **kwargs)
        elif cmd == "T":
            table_chat(args, client=client, **kwargs)
        elif cmd == "Q":
            break

        if client and client._loop:
            client._loop.run_until_complete(asyncio.sleep(0.1))

    return True
