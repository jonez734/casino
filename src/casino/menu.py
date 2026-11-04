from bbsengine6 import io, member, register, util
from bbsengine6.menu_next import MenuOption, read_menu

from . import lib as libcasino
from .dal import player as dal_player

__version__ = "202210010112"


def init(args, **kw: dict) -> bool:
    register(
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


def _blackjack(args, **kw):
    io.echo("blackjack")
    libcasino.runmodule(args, "blackjack")


def _stats(args, **kw):
    show_player_stats(args, **kw)


def _exit(args, **kw):
    return None


def root_menu(**kw):
    """The casino root menu. Each option carries its own action; X is the protected exit, Q its alias."""
    return (
        MenuOption(letter="B", label="Blackjack", action=lambda args: _blackjack(args, **kw)),
        MenuOption(letter="S", label="Stats", action=lambda args: _stats(args, **kw)),
        MenuOption(letter="X", label="Exit", aliases=("Q",), action=lambda args: _exit(args)),
    )


def main(args, **kw):
    util.heading("casino")
    libcasino.setarea(args, "casino")
    io.echo("{optioncolor}[B]{labelcolor} Blackjack")
    io.echo("{optioncolor}[S]{labelcolor} Stats")
    io.echo("{f6}{optioncolor}[X]{labelcolor} Exit{f6}")

    # Re-read until the exit runs. X and Q are the exit; Enter takes X as the default.
    while True:
        choice = read_menu(
            "{var:promptcolor}casino {var:optioncolor}[BSXQ]{var:promptcolor}: {var:inputcolor}",
            root_menu(**kw),
            state=args,
            mode="key",
            default="X",
            reader=io.inputchoice,
        )
        if choice.key == "X":
            return True
