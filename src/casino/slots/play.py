# casino/slots/play.py
# Door-mode play loop for slots. Mirrors blackjack/play.py.

from __future__ import annotations

from typing import Any, Optional

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


def run_one_spin(player: SlotPlayer) -> dict:
    """Prompt for a bet, run one spin, render the result.

    Returns the SpinResult on success, or ``None`` if the player chose to
    quit / bet validation failed at the prompt.
    """
    bet = io.inputinteger(
        "{var:promptcolor}Bet (q to quit): {var:inputcolor}",
        minimum=player.min_bet,
        maximum=min(player.max_bet, player.credits),
    )
    if bet is None:
        return None
    err = player.validate_bet(bet)
    if err is not None:
        io.echo(f"{{error}}{err}{{normal}}")
        return None
    result = player.play(bet)
    io.echo("{title}Spin result:{normal}")
    io.echo(render_ascii(result))
    if result.did_win:
        io.echo(f"{{success}}Won {result.payout}!{{normal}}  net: {result.net:+d}")
    else:
        io.echo(f"{{error}}No win.{{normal}}  net: {result.net:+d}")
    io.echo(f"Credits: {player.credits}")
    return result


def main(args: Any, **kw: dict) -> bool:
    player: Optional[SlotPlayer] = kw.get("player")
    dealer: Optional[SlotDealer] = kw.get("dealer")
    if player is None or dealer is None:
        io.echo(
            "{error}Error: missing required arguments (player, dealer){normal}"
        )
        return False

    util.heading("play slots")
    io.echo(f"Credits: {player.credits}   Bet limits: {player.min_bet}–{player.max_bet}")

    while True:
        result = run_one_spin(player)
        if result is None:
            return True
        again = io.inputboolean(
            "{var:promptcolor}spin again? {var:optioncolor}[Yn]{var:promptcolor}: {var:inputcolor}",
            "Y",
        )
        if again is False:
            return True
