from bbsengine6 import register_module


__version__ = "202210010112"

__all__ = ["lib", "dealer", "player", "play", "game"]


def init(args, **kw: dict) -> bool:
    register_module(
        name="casino.slots",
        module_path="casino.slots",
        version=__version__,
        apis={},
    )
    return True  # type: ignore[return-value]


def access(args, op: str, **kw: dict) -> bool:
    return True


def buildargs(args, **kw):
    return None


def main(args, **kw):
    from . import game
    return game.main(args, **kw)
