# commands/poker/__init__.py
# Poker commands: hand actions, table management, and the table list.

from bbsengine6 import io

from casino.commands import _common

from . import lib

__version__ = "202406010000"

SUBCOMMANDS = {
    "check": lib.check,
    "call": lib.call,
    "bet": lib.bet,
    "raise": lib.raise_bet,
    "fold": lib.fold,
    "allin": lib.all_in,
    # "hand" shows the player's own cards, which poker_get_state already carries.
    "hand": lib.show_table,
    "table": lib.show_table,
    "create": lib.create_table,
    "join": lib.join_table,
    "leave": lib.leave_table,
    "list": lib.list_tables,
    "start": lib.start_hand,
}


def _echo_error(message):
    """Report an ambiguous subcommand through this package's own ``io``."""
    io.echo(message, level="error")


def _resolve_subcommand(input_str):
    """Resolve a typed subcommand against this package's SUBCOMMANDS. See ``_common``."""
    return _common.resolve_subcommand(input_str, SUBCOMMANDS, report=_echo_error)


def init(args, **kw) -> bool:
    return _common.register(
        name="casino.poker",
        module_path="casino.commands.poker",
        version=__version__,
    )


def access(args, op: str, **kw) -> bool:
    return True


def version(args, **kw) -> str:
    return __version__


def buildargs(args, **kw):
    return _common.build_parser("poker", subcommands=SUBCOMMANDS)


def main(args, **kw) -> bool:
    return _common.dispatch(
        args,
        SUBCOMMANDS,
        menu=lib.menu,
        version_text=__version__,
        name="poker",
        **kw,
    )
