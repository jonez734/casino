# commands/chat/lib.py
# Chat command functions

import asyncio

from bbsengine6 import io


def get_client():
    from casino.connect import get_client as _get_client

    return _get_client()


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
    if client.current_table is None:
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
        cmd = io.inputchoice("{var:promptcolor}[G]lobal  [T]able  [Q]uit: {var:inputcolor}", "g,t,q", default="q")

        if cmd == "G":
            chat(args, client=client, **kwargs)
        elif cmd == "T":
            table_chat(args, client=client, **kwargs)
        elif cmd == "Q":
            break

        if client and client._loop:
            client._loop.run_until_complete(asyncio.sleep(0.1))

    return True
