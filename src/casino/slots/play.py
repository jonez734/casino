# casino/slots/play.py
# Door-mode play loop for slots. Mirrors blackjack/play.py.

from __future__ import annotations

from typing import Any

from bbsengine6 import io, util

from .dealer import SlotDealer
from .lib import render_ascii
from .player import SlotPlayer


def init(args: Any, **kw: dict) -> bool:
    return True


def access(args: Any, op: str, **kw: dict) -> bool:
    return True


def buildargs(args: Any = None, **kw: dict) -> None:
    return None


def _render_bet_help(**kwargs) -> None:
    """F1/HELP callback for the bet prompt.

    Per the spec: util.heading() is called exactly once per display of
    help, then the option list is echoed.
    """
    util.heading("play slots")
    io.echo("{var:optioncolor}[B]{var:labelcolor}et an amount (within table min/max and your credits)")
    io.echo("{var:optioncolor}[Q]{var:labelcolor}uit to main menu")


def _render_again_help(**kwargs) -> None:
    """F1/HELP callback for the spin-again prompt.

    Per the spec: util.heading() is called exactly once per display of
    help, then the option list is echoed.
    """
    util.heading("play slots")
    io.echo("{var:optioncolor}[Y]{var:labelcolor}es, spin again")
    io.echo("{var:optioncolor}[N]{var:labelcolor}o, return to main menu")


def _prompt_bet(player: SlotPlayer) -> int | None:
    """Ask the player for a bet. Returns the bet or None if the player quit."""
    while True:
        choice = io.inputchoice(
            "{var:promptcolor}Bet (q to quit): {var:inputcolor}",
            "b,q",
            default="b",
            help=_render_bet_help,
        )
        if choice == "Q":
            return None
        bet = io.inputinteger(
            f"{{var:promptcolor}}Bet amount ({player.min_bet}-{min(player.max_bet, player.credits)}): {{var:inputcolor}}",
            minimum=player.min_bet,
            maximum=min(player.max_bet, player.credits),
        )
        if bet is None:
            return None
        err = player.validate_bet(bet)
        if err is not None:
            io.echo(f"{{level.error}}{err}{{var:normalcolor}}")
            continue
        return bet


def run_one_spin(player: SlotPlayer) -> dict | None:
    """Prompt for a bet, run one spin, render the result.

    Returns the SpinResult on success, or ``None`` if the player chose to
    quit / bet validation failed at the prompt.
    """
    bet = _prompt_bet(player)
    if bet is None:
        return None
    result = player.play(bet)
    io.echo("{var:titlecolor}Spin result:{var:normalcolor}")
    io.echo("{/all}")
    io.echo(render_ascii(result))
    if result.did_win:
        io.echo(f"{{level.ok}}Won {result.payout}!{{var:normalcolor}}  net: {result.net:+d}")
    else:
        io.echo(f"{{level.error}}No win.{{var:normalcolor}}  net: {result.net:+d}")
    io.echo(f"Credits: {player.credits}")
    return result


def main(args: Any, **kw: dict) -> bool:
    player: SlotPlayer | None = kw.get("player")
    dealer: SlotDealer | None = kw.get("dealer")
    if player is None or dealer is None:
        io.echo(
            "{level.error}Error: missing required arguments (player, dealer){var:normalcolor}"
        )
        return False

    util.heading("play slots")
    io.echo(f"Credits: {player.credits}   Bet limits: {player.min_bet}–{player.max_bet}")

    while True:
        result = run_one_spin(player)
        if result is None:
            return True
        again = io.inputchoice(
            "{var:promptcolor}spin again? {var:optioncolor}[Yn]{var:promptcolor}: {var:inputcolor}",
            "y,n",
            default="y",
            help=_render_again_help,
        )
        if again == "N":
            return True
