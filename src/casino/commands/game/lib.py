# commands/game/lib.py
# Game command functions

import asyncio

from bbsengine6 import io


def get_client():
    from casino.connect import get_client as _get_client

    return _get_client()


def bet(args, client=None, **kwargs) -> bool:
    """Place a bet."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    client.cmd_bet()
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def hit(args, client=None, **kwargs) -> bool:
    """Hit (blackjack)."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    client._loop.run_until_complete(client.send({"type": "hit"}))
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def stand(args, client=None, **kwargs) -> bool:
    """Stand (blackjack)."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    client._loop.run_until_complete(client.send({"type": "stand"}))
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def double(args, client=None, **kwargs) -> bool:
    """Double down (blackjack)."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    client._loop.run_until_complete(client.send({"type": "double"}))
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def split(args, client=None, **kwargs) -> bool:
    """Split hand (blackjack)."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    client._loop.run_until_complete(client.send({"type": "split"}))
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def game_action(args, action: str, client=None, **kwargs) -> bool:
    """Send a game action (check, bet, call, raise, fold, etc.)."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    client._loop.run_until_complete(client.send({"type": action}))
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def play(args, client=None, **kwargs) -> bool:
    """Play a game action - dynamically selected from available_actions."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    if client.current_table is None:
        io.echo("Not at a table.", level="error")
        return False

    actions = client.last_available_actions or []
    if not actions:
        io.echo("No actions available. Join a table first.")
        return False

    from casino.connect import ActionInputHandler

    handler = ActionInputHandler(
        [{"action": a, "hotkey": "", "label": a} for a in actions]
    )
    action = io.inputstring("Action: ", completer=handler.get_completer())

    resolved = handler.resolve(action)
    if resolved:
        client._loop.run_until_complete(client.send({"type": resolved}))
        client._loop.run_until_complete(asyncio.sleep(0.1))
        return True
    io.echo("Invalid action.")
    return False


def menu(args, client=None, **kwargs):
    """Show game operations submenu."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False

    while True:
        cmd = io.inputchoice(
            "{var:promptcolor}[B]et  [H]it  [S]tand  [D]ouble  [P]lay  [L]Split  [Q]uit: {var:inputcolor}", "b,h,s,d,p,l,q", default="q"
        )

        if cmd == "B":
            bet(args, client=client, **kwargs)
        elif cmd == "H":
            hit(args, client=client, **kwargs)
        elif cmd == "S":
            stand(args, client=client, **kwargs)
        elif cmd == "D":
            double(args, client=client, **kwargs)
        elif cmd == "L":
            split(args, client=client, **kwargs)
        elif cmd == "P":
            play(args, client=client, **kwargs)
        elif cmd == "Q":
            break

        if client and client._loop:
            client._loop.run_until_complete(asyncio.sleep(0.1))

    return True
