# commands/game/__init__.py
# Game commands module: the seat-gated actions shared by the blackjack and
# poker tables (bet, hit, stand, double, split, play).

from bbsengine6 import io

from casino.commands import _common

from . import lib

__version__ = "202210010112"

SUBCOMMANDS = {
    "bet": lib.bet,
    "hit": lib.hit,
    "stand": lib.stand,
    "double": lib.double,
    "split": lib.split,
    "play": lib.play,
}


def _echo_error(message):
    """Report an ambiguous subcommand through this package's own ``io``."""
    io.echo(message, level="error")


def _resolve_subcommand(input_str):
    """Resolve a typed subcommand against this package's SUBCOMMANDS. See ``_common``."""
    return _common.resolve_subcommand(input_str, SUBCOMMANDS, report=_echo_error)


def init(args, **kw) -> bool:
    return _common.register(
        name="casino.game",
        module_path="casino.commands.game",
        version=__version__,
    )


def access(args, op: str, **kw) -> bool:
    return True


def version(args, **kw) -> str:
    return __version__


def buildargs(args, **kw):
    def extra(parser):
        # ``game bet 5``: the amount is optional; with none, bet prompts for it.
        parser.add_argument("amount", nargs="?", type=int, default=None, help="bet amount (bet only)")

    return _common.build_parser("game", subcommands=SUBCOMMANDS, extra=extra)


def main(args, **kw) -> bool:
    return _common.dispatch(
        args,
        SUBCOMMANDS,
        menu=lib.menu,
        version_text=__version__,
        name="game",
        **kw,
    )
