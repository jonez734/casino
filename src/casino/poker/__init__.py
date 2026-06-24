from bbsengine6 import io, register_module


__version__ = "202406010000"

from casino.poker.variant import get_variant, list_variants, VARIANTS, BaseVariant, VariantRegistry
from casino.poker.lib import (
    BettingStructure,
    BettingStreet,
    BetLimits,
    HandRank,
    PokerDeck,
    PokerCard,
    SUITS,
    RANKS,
)
from casino.poker.dealer import PokerDealer
from casino.poker.player import PokerPlayer


def init(args, **kw: dict) -> bool:
    register_module(
        name="casino.poker",
        module_path="casino.poker",
        version=__version__,
        apis={},
    )
    return True


def access(args, op: str, **kw: dict) -> bool:
    return True


def buildargs(args, **kw):
    return None


def main(args, **kw):
    io.echo("poker module")
    io.echo("Use 'poker holdem', 'poker omaha', or 'poker stud' to play")
    return True
