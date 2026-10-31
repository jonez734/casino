# commands/tictactoe/lib.py
# Tic-tac-toe command functions. Each one sends the bed-side message the server
# handles (tictactoe/api_handler.py). The client is the connected CasinoClient.

from bbsengine6 import io

from casino.commands import _common


def _send(client, message: dict) -> bool:
    client._loop.run_until_complete(client.send(message))
    return True


def quickplay(args, client=None, **kwargs) -> bool:
    """Start a quick game: lazy-create the table and start a session."""
    client = client or _common.get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    return _send(client, {"type": "tictactoe_quick_play"})


def move(args, client=None, **kwargs) -> bool:
    """Place a mark. Prompts for a cell 0-8."""
    client = client or _common.get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    raw = io.inputstring("Cell [0-8]: ").strip()
    if not raw.isdigit() or not 0 <= int(raw) <= 8:
        io.echo("Cell must be 0-8.", level="error")
        return False
    return _send(client, {"type": "tictactoe_move", "cell": int(raw)})


def join(args, client=None, **kwargs) -> bool:
    """Take the O seat in a two-human game."""
    client = client or _common.get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    return _send(client, {"type": "tictactoe_join"})


def resign(args, client=None, **kwargs) -> bool:
    """Forfeit the current game."""
    client = client or _common.get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    return _send(client, {"type": "tictactoe_resign"})


def menu(args, **kwargs) -> None:
    """Submenu shown when ``tictactoe`` is given no subcommand."""
    io.echo("tictactoe: quickplay, move, join, resign")
