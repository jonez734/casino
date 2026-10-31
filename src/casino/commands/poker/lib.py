# commands/poker/lib.py
# Poker command functions

import asyncio

from bbsengine6 import io
from casino import host

from casino.poker import list_variants

# Shared helpers live in commands/_common.py. The underscore names are kept so
# existing callers and tests keep working.
from casino.commands._common import get_client as get_client  # noqa: E402


def send_action(action: str, data: dict = None, client=None):
    """Send an action to the poker service, on ``client`` (or the connected client)."""
    client = client or get_client()
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
    return send_action("poker_check", client=client)


def call(args, client=None, **kwargs) -> bool:
    """Call the current bet."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    return send_action("poker_call", client=client)


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

    return send_action("poker_bet", {"amount": amount}, client=client)


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

    return send_action("poker_raise", {"amount": amount}, client=client)


def fold(args, client=None, **kwargs) -> bool:
    """Fold your hand."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    return send_action("poker_fold", client=client)


def all_in(args, client=None, **kwargs) -> bool:
    """Go all-in."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    return send_action("poker_all_in", client=client)


def show_table(args, client=None, **kwargs) -> bool:
    """Show current table state."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False

    client._loop.run_until_complete(client.send({"type": "poker_get_state"}))
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
    return send_action("poker_leave_table", client=client)


def list_tables(args, client=None, **kwargs) -> bool:
    """List available poker tables."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False

    client._loop.run_until_complete(client.send({"type": "list_tables", "game_type": "poker"}))
    client._loop.run_until_complete(asyncio.sleep(0.1))
    return True


def start_hand(args, client=None, **kwargs) -> bool:
    """Start a new hand (requires all players ready)."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False
    return send_action("poker_start_hand", client=client)


def play(args, client=None, **kwargs) -> bool:
    """Sit down at a poker table and play.

    Creates a fresh holdem table with $1/$2 blinds, seats the player with a default buy-in,
    and opens the poker menu on that table. Other players can join the table by moniker
    through the menu's Join command.
    """
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False

    buy_in = io.inputinteger("{var:promptcolor}Buy-in: {var:inputcolor}", 100)
    if buy_in <= 0:
        io.echo("Invalid buy-in.")
        return False

    client._loop.run_until_complete(client.send({
        "type": "poker_create_table",
        "variant": "holdem",
        "betting_structure": "no_limit",
        "small_blind": 1,
        "big_blind": 2,
    }))
    client._loop.run_until_complete(asyncio.sleep(0.1))
    table = getattr(client, "last_poker_table", None)
    if not table:
        io.echo("{errorcolor}Could not create a table.{/all}")
        return False

    client._loop.run_until_complete(client.send({
        "type": "poker_join_table",
        "table_moniker": table,
        "buy_in": buy_in,
    }))
    client._loop.run_until_complete(asyncio.sleep(0.1))
    client.current_table_moniker = table
    io.echo(f"{{title}}Playing at {table}. Use [S]tart to deal the first hand once others join.{{normal}}")
    return menu(args, client=client, **kwargs)


def menu(args, client=None, **kwargs):
    """Show poker operations submenu."""
    client = client or get_client()
    if client is None:
        io.echo("Not connected. Use Connect first.", level="error")
        return False

    while True:
        # host.choose: LO when hosted, io.inputchoice standalone. Uppercased for the checks below.
        cmd = (host.choose(
            "{var:promptcolor}[S]tart  [C]heck  [L]call  [B]et  [R]aise  [A]ll-in  [F]old  "
            "[T]able  [Q]uit: {var:inputcolor}",
            "s,c,l,b,r,a,f,t,q",
            default="q"
        ) or "").upper()

        if cmd == "S":
            start_hand(args, client=client, **kwargs)
        elif cmd == "C":
            check(args, client=client, **kwargs)
        elif cmd == "L":
            call(args, client=client, **kwargs)
        elif cmd == "B":
            bet(args, client=client, **kwargs)
        elif cmd == "R":
            raise_bet(args, client=client, **kwargs)
        elif cmd == "A":
            all_in(args, client=client, **kwargs)
        elif cmd == "F":
            fold(args, client=client, **kwargs)
        elif cmd == "T":
            show_table(args, client=client, **kwargs)
        elif cmd == "Q":
            break

        if client and client._loop:
            client._loop.run_until_complete(asyncio.sleep(0.1))

    return True
