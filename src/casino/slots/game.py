# casino/slots/game.py
# Top-level entry: wires up a SlotDealer + SlotPlayer and runs the door loop.

from __future__ import annotations

from typing import Any

from bbsengine6 import io, member

from . import lib as slots_lib
from .dealer import SlotDealer
from .player import SlotPlayer


__version__ = "202210010112"


def init(args: Any, **kw: dict) -> bool:
    return True


def access(args: Any, op: str, **kw: dict) -> bool:
    return True


def buildargs(args: Any = None, **kw: dict) -> None:
    return None


def main(args: Any, **kw: dict) -> bool:
    io.terminal.title("slots")
    memberid = member.getcurrentid(args)
    if not memberid:
        io.echo("{error}Could not determine current member.{normal}")
        return False

    # In the simple door-mode flow, the player's credit balance comes from
    # the bank module; we mirror the blackjack approach of trusting the
    # caller's pre-loaded context.
    credits = int(kw.get("credits", 0))
    min_bet = int(kw.get("min_bet", 1))
    max_bet = int(kw.get("max_bet", 1000))

    rng = slots_lib.RNG()
    dealer = SlotDealer(
        reels=slots_lib.default_reels(slots_lib.DEFAULT_SYMBOLS, rng),
        paytable=slots_lib.Paytable(),
        rng=rng,
    )
    player = SlotPlayer(
        moniker=memberid,
        credits=credits,
        dealer=dealer,
        min_bet=min_bet,
        max_bet=max_bet,
    )

    from . import play as slots_play

    return slots_play.main(args, player=player, dealer=dealer, **kw)
