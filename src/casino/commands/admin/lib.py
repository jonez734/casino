# commands/admin/lib.py
# Admin command functions

import asyncio

from bbsengine6 import io


def get_client():
    from casino.connect import get_client as _get_client

    return _get_client()


def watch_table(args, client=None, **kwargs) -> bool:
    """Watch a table."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    moniker = io.inputstring("Table moniker to watch: ").strip()
    if not moniker:
        io.echo("Cancelled.", level="error")
        return False
    client._loop.run_until_complete(
        client.send({"type": "watch_table", "moniker": moniker})
    )
    client.watched_tables.add(moniker)
    io.echo(f"Now watching table {moniker}")
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def unwatch_table(args, client=None, **kwargs) -> bool:
    """Stop watching a table."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    moniker = io.inputstring("Table moniker to stop watching: ").strip()
    if not moniker:
        io.echo("Cancelled.", level="error")
        return False
    client._loop.run_until_complete(
        client.send({"type": "unwatch_table", "moniker": moniker})
    )
    client.watched_tables.discard(moniker)
    io.echo(f"No longer watching table {moniker}")
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def kick_player(args, client=None, **kwargs) -> bool:
    """Kick a player from table(s)."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False

    table_input = getattr(args, "tables", None)
    player_moniker = getattr(args, "player", None)

    if not table_input or not player_moniker:
        table_input = io.input("Table moniker(s) or 'all': ").strip()
        if not table_input:
            io.echo("Cancelled.", level="error")
            return False

        player_moniker = io.input("Player to kick: ").strip()
        if not player_moniker:
            io.echo("Cancelled.", level="error")
            return False

    if table_input.lower() == "all":
        table_monikers = ["all"]
    else:
        table_monikers = [t.strip() for t in table_input.split(",") if t.strip()]

    if not table_monikers:
        io.echo("Cancelled.", level="error")
        return False

    client._loop.run_until_complete(
        client.send({
            "type": "kick_player",
            "table_monikers": table_monikers,
            "player_moniker": player_moniker,
        })
    )
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True
#
# def unban_player(args, client=None, **kwargs) -> bool:
#     """Unban a player."""
#     pass
#
# def disconnect_player(args, client=None, **kwargs) -> bool:
#     """Force disconnect a player."""
#     pass
#
# def show_connections(args, client=None, **kwargs) -> bool:
#     """Show active connections."""
#     pass


def menu(args, client=None, **kwargs):
    """Show admin operations submenu."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False

    while True:
        cmd = io.inputchoice("{var:promptcolor}[W]atch  [U]nwatch  [K]ick  [Q]uit: {var:inputcolor}", "w,u,k,q", default="q")

        if cmd == "W":
            watch_table(args, client=client, **kwargs)
        elif cmd == "U":
            unwatch_table(args, client=client, **kwargs)
        elif cmd == "K":
            kick_player(args, client=client, **kwargs)
        elif cmd == "Q":
            break

        if client and client._loop:
            client._loop.run_until_complete(asyncio.sleep(0.1))

    return True
