# commands/table/lib.py
# Table command functions

import asyncio

from bbsengine6 import io


def get_client():
    from casino.connect import get_client as _get_client

    return _get_client()


def list_tables(args, client=None, **kwargs) -> bool:
    """List available tables."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    client.cmd_list_tables()
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def create_table(args, client=None, **kwargs) -> bool:
    """Create a new table."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    client.cmd_create_table()
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def update_table(args, client=None, **kwargs) -> bool:
    """Update table settings."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    client.cmd_update_table()
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def join_table(args, client=None, **kwargs) -> bool:
    """Join a table."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    client.cmd_join_table()
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def leave_table(args, client=None, **kwargs) -> bool:
    """Leave current table."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    client.cmd_leave_table()
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def view_table(args, client=None, **kwargs) -> bool:
    """View current table status."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    if client.current_table is None:
        io.echo("Not at a table.", level="error")
        return False
    client._loop.run_until_complete(
        client.send({"type": "view_table", "table_id": client.current_table})
    )
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def menu(args, client=None, **kwargs):
    """Show table operations submenu."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False

    while True:
        cmd = io.inputchoice(
            "{var:promptcolor}[T]ables  [C]reate  [J]oin  [L]eave  [U]pdate  [V]iew  [Q]uit: {var:inputcolor}",
            "t,c,j,l,u,v,q",
            default="q",
        )

        if cmd == "T":
            list_tables(args, client=client, **kwargs)
        elif cmd == "C":
            create_table(args, client=client, **kwargs)
        elif cmd == "J":
            join_table(args, client=client, **kwargs)
        elif cmd == "L":
            leave_table(args, client=client, **kwargs)
        elif cmd == "U":
            update_table(args, client=client, **kwargs)
        elif cmd == "V":
            view_table(args, client=client, **kwargs)
        elif cmd == "Q":
            break

        if client and client._loop:
            client._loop.run_until_complete(asyncio.sleep(0.1))

    return True
