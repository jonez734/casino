from bbsengine6 import register_module

from . import lib
from .hand import Hand
from .phase import GamePhase

__version__ = "202210010112"

__all__ = ["Hand", "GamePhase"]


def init(args, **kw: dict) -> bool:
    register_module(
        name="casino.blackjack",
        module_path="casino.blackjack",
        version=__version__,
        apis={},
    )
    return True  # type: ignore[return-value]


def access(args, op: str, **kw: dict) -> bool:
    return True


def buildargs(args, **kw: dict):
    return None


def main(args, **kw):
    from bbsengine6 import module

    return module.run(args, "game", package="casino.blackjack", **kw)
