from bbsengine6 import util, io, register_module

from . import lib as libcasino


__version__ = "202210010112"


def init(args, **kw: dict) -> bool:
    register_module(
        name="casino.menu",
        module_path="casino.menu",
        version=__version__,
        apis={},
    )
    return True  # type: ignore[return-value]


def access(args, op: str, **kw: dict) -> bool:
    return True


def buildargs(args, **kw: dict) -> bool:
    return None


def main(args, **kw):
    util.heading("casino")
    libcasino.setarea(args, "casino")
    io.echo("{optioncolor}[B]{labelcolor} Blackjack")
    io.echo("{f6}{optioncolor}[X]{labelcolor} Exit{f6}")

    done = False
    while not done:
        ch = io.inputchar(
            "{promptcolor}casino {optioncolor}[BXQ]{promptcolor}: {inputcolor}",
            "BX",
            "X",
        )
        if ch == "B":
            io.echo("blackjack")
            libcasino.runmodule(args, "blackjack")
        elif ch == "X" or ch == "Q":
            done = True
        else:
            io.echo("{bell}")
    return True
