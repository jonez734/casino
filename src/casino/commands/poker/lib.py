# commands/poker/lib.py
# Poker command functions

import asyncio

from bbsengine6 import io
from casino.poker import list_variants


def get_client():
    from casino.connect import get_client as _get_client
    return _get_client()


def send_action(action: str, data: dict = None):
    """Send an action to the poker service."""
    client = get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return None

    msg = {"type": action}
    if data:
        msg.update(data)

    try:
        client._loop.run_until_complete(client.send(msg))
        client._loop.run_until_complete(asyncio.sleep(0.1))
    except Exception as e:
        io.echo(f"Error sending {action}: {e}", level="error")

    return True


def check(args, client=None, **kwargs) -> bool:
    """Check (call if no bet)."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    return send_action("poker_check")


def call(args, client=None, **kwargs) -> bool:
    """Call the current bet."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    return send_action("poker_call")


def bet(args, client=None, **kwargs) -> bool:
    """Place a bet."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False

    amount = io.inputinteger("{var:promptcolor}Bet amount: {var:inputcolor}", 0)
    if amount <= 0:
        io.echo("Invalid bet amount.")
        return False

    return send_action("poker_bet", {"amount": amount})


def raise_bet(args, client=None, **kwargs) -> bool:
    """Raise the current bet."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False

    amount = io.inputinteger("{var:promptcolor}Raise to: {var:inputcolor}", 0)
    if amount <= 0:
        io.echo("Invalid raise amount.")
        return False

    return send_action("poker_raise", {"amount": amount})


def fold(args, client=None, **kwargs) -> bool:
    """Fold your hand."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    return send_action("poker_fold")


def all_in(args, client=None, **kwargs) -> bool:
    """Go all-in."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    return send_action("poker_all_in")


def show_hand(args, client=None, **kwargs) -> bool:
    """Show your hand at showdown."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    return send_action("poker_show_hand")


def muck_hand(args, client=None, **kwargs) -> bool:
    """Muck (don't show) your hand."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    return send_action("poker_muck_hand")


def show_my_hand(args, client=None, **kwargs) -> bool:
    """Show your current hand."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False

    client._loop.run_until_complete(client.send({"type": "poker_get_hand"}))
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def show_table(args, client=None, **kwargs) -> bool:
    """Show current table state."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False

    client._loop.run_until_complete(client.send({"type": "poker_get_state"}))
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def list_players(args, client=None, **kwargs) -> bool:
    """List players at the table."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False

    client._loop.run_until_complete(client.send({"type": "poker_list_players"}))
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def show_deck(args, client=None, **kwargs) -> bool:
    """Show deck status."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False

    client._loop.run_until_complete(client.send({"type": "poker_get_deck"}))
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def create_table(args, client=None, **kwargs) -> bool:
    """Create a new poker table."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False

    io.echo("{title}Create Poker Table{normal}")
    io.echo(f"Available variants: {', '.join(list_variants())}")

    variant = io.inputstring("{var:promptcolor}Variant (holdem): {var:inputcolor}", "holdem")
    betting = io.inputstring("{var:promptcolor}Betting (no_limit): {var:inputcolor}", "no_limit")
    sb = io.inputinteger("{var:promptcolor}Small blind: {var:inputcolor}", 1)
    bb = io.inputinteger("{var:promptcolor}Big blind: {var:inputcolor}", 2)

    client._loop.run_until_complete(client.send({
        "type": "poker_create_table",
        "variant": variant or "holdem",
        "betting_structure": betting or "no_limit",
        "small_blind": sb,
        "big_blind": bb,
    }))
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def join_table(args, client=None, **kwargs) -> bool:
    """Join a poker table."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False

    table_moniker = io.inputstring("{var:promptcolor}Table moniker: {var:inputcolor}", "")
    if not table_moniker:
        io.echo("Table moniker required.")
        return False

    buy_in = io.inputinteger("{var:promptcolor}Buy-in: {var:inputcolor}", 100)

    client._loop.run_until_complete(client.send({
        "type": "poker_join_table",
        "table_moniker": table_moniker,
        "buy_in": buy_in,
    }))
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def leave_table(args, client=None, **kwargs) -> bool:
    """Leave the current table."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    return send_action("poker_leave_table")


def list_tables(args, client=None, **kwargs) -> bool:
    """List available poker tables."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False

    client._loop.run_until_complete(client.send({"type": "poker_list_tables"}))
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def start_hand(args, client=None, **kwargs) -> bool:
    """Start a new hand (requires all players ready)."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    return send_action("poker_start_hand")


def menu(args, client=None, **kwargs):
    """Show poker operations submenu."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False

    while True:
        cmd = io.inputchoice(
            "{var:promptcolor}[C]heck  [A]ll  [B]et  [R]aise  [F]old  "
            "[H]and  [T]able  [L]ist  [Q]uit: {var:inputcolor}",
            "c,a,b,r,f,h,t,l,q",
            default="q"
        )

        if cmd == "C":
            check(args, client=client, **kwargs)
        elif cmd == "A":
            all_in(args, client=client, **kwargs)
        elif cmd == "B":
            bet(args, client=client, **kwargs)
        elif cmd == "R":
            raise_bet(args, client=client, **kwargs)
        elif cmd == "F":
            fold(args, client=client, **kwargs)
        elif cmd == "H":
            show_my_hand(args, client=client, **kwargs)
        elif cmd == "T":
            show_table(args, client=client, **kwargs)
        elif cmd == "L":
            list_tables(args, client=client, **kwargs)
        elif cmd == "Q":
            break

        if client and client._loop:
            client._loop.run_until_complete(asyncio.sleep(0.1))

    return True
