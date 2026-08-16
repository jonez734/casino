# casino/yahtzee/game.py
# Top-level entry: wires up a YahtzeeDealer + YahtzeePlayer and runs the
# door-mode play loop. Mirrors casino/slots/game.py.

from bbsengine6 import io, member, register_module

from . import lib as yahtzee_lib
from .dealer import YahtzeeDealer
from .player import YahtzeePlayer

__version__ = "202601011200"


def init(args, **kw: dict) -> bool:
    register_module(
        name="casino.yahtzee.game",
        module_path="casino.yahtzee.game",
        version=__version__,
        apis={},
    )
    return True  # type: ignore[return-value]


def access(args, op: str, **kw: dict) -> bool:
    return True


def buildargs(args, **kw: dict):
    return None


def main(args, **kw) -> bool:
    io.terminal.title("yahtzee")
    memberid = member.getcurrentid(args)
    if not memberid:
        io.echo("{error}Could not determine current member.{normal}")
        return False

    credits = int(kw.get("credits", 0))
    bet_amount = int(kw.get("bet_amount", yahtzee_lib.MIN_BET))
    min_bet = int(kw.get("min_bet", yahtzee_lib.MIN_BET))
    max_bet = int(kw.get("max_bet", yahtzee_lib.MAX_BET))

    dealer = YahtzeeDealer()
    player = YahtzeePlayer(
        moniker=memberid,
        credits=credits,
        bet_amount=bet_amount,
        min_bet=min_bet,
        max_bet=max_bet,
    )

    from . import play as yahtzee_play

    return yahtzee_play.main(args, player=player, dealer=dealer, **kw)
