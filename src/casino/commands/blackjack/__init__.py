# commands/blackjack/__init__.py
# Blackjack commands.

from bbsengine6 import io

from casino.commands import _common

from . import lib

__version__ = "202406010000"

SUBCOMMANDS = {
    "play": lib.play,
}

# The verbs a seated blackjack table accepts through ``table <verb>``. The implementations are the game
# package's, so the blackjack table and the game command run the same code.
from casino.commands.game import lib as _game_lib  # noqa: E402

TABLE_VERBS = {
    "bet": _game_lib.bet,
    "hit": _game_lib.hit,
    "stand": _game_lib.stand,
    "double": _game_lib.double,
    "split": _game_lib.split,
    "play": _game_lib.play,
}


def _echo_error(message):
    """Report an ambiguous subcommand through this package's own ``io``."""
    io.echo(message, level="error")


def _resolve_subcommand(input_str):
    """Resolve a typed subcommand against this package's SUBCOMMANDS. See ``_common``."""
    return _common.resolve_subcommand(input_str, SUBCOMMANDS, report=_echo_error)


def init(args, **kw) -> bool:
    return _common.register(
        name="casino.blackjack",
        module_path="casino.commands.blackjack",
        version=__version__,
    )


def access(args, op: str, **kw) -> bool:
    return True


def version(args, **kw) -> str:
    return __version__


def buildargs(args, **kw):
    return _common.build_parser("blackjack", subcommands=SUBCOMMANDS)


def main(args, **kw) -> bool:
    return _common.dispatch(
        args,
        SUBCOMMANDS,
        menu=lib.menu,
        version_text=__version__,
        name="blackjack",
        **kw,
    )
