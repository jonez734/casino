from bbsengine6 import register_module

from . import lib


__version__ = "202210010112"


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


def buildargs(args, **kw: dict) -> bool:
    return None


def main(args, **kw):
    lib.runmodule(args, "main", **kw)
    return True
