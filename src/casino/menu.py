from bbsengine6 import io, member, register_module, util

from . import lib as libcasino
from .dal import player as dal_player

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


def show_player_stats(args, **kw) -> None:
    """Display game stats for the current BBS member."""
    pool = kw.get("pool")
    moniker = member.getcurrentmoniker(args, pool=pool)
    if not moniker:
        io.echo("{level.error}not logged in{var:normalcolor}")
        return

    util.heading(f"stats for {moniker}")
    try:
        stats = dal_player.get_player_stats(args, moniker)
    except Exception as exc:
        io.echo("{level.error}could not load stats: {exc}{var:normalcolor}".format(exc=exc))
        return

    if not stats:
        io.echo("{var:labelcolor}no stats recorded yet.{var:normalcolor}")
        return

    width = max(len(name) for name in stats)
    for name in sorted(stats):
        value = stats[name]
        io.echo(
            "{var:optioncolor}" + name.ljust(width)
            + "{var:normalcolor} {var:valuecolor}" + str(value)
        )


def main(args, **kw):
    util.heading("casino")
    libcasino.setarea(args, "casino")
    io.echo("{optioncolor}[B]{labelcolor} Blackjack")
    io.echo("{optioncolor}[S]{labelcolor} Stats")
    io.echo("{f6}{optioncolor}[X]{labelcolor} Exit{f6}")

    done = False
    while not done:
        ch = io.inputchar(
            "{var:promptcolor}casino {var:optioncolor}[BSXQ]{var:promptcolor}: {var:inputcolor}",
            "BSX",
            "X",
        )
        if ch == "B":
            io.echo("blackjack")
            libcasino.runmodule(args, "blackjack")
        elif ch == "S":
            show_player_stats(args, **kw)
        elif ch == "X" or ch == "Q":
            done = True
        else:
            io.echo("{bell}")
    return True
