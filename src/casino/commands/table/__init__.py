# commands/table/__init__.py
# Table commands: list, create, update, join, leave, view.

import argparse

from bbsengine6 import io  # noqa: F401  (kept: tests patch io on this package)

from casino.commands import _common

from . import lib

__version__ = "202210010112"

SUBCOMMANDS = {
    "list": lib.list_tables,
    "create": lib.create_table,
    "join": lib.join_table,
    "leave": lib.leave_table,
    "view": lib.view_table,
    "update": lib.update_table,
}

GAME_TYPES = ("blackjack", "poker", "slots", "yahtzee", "tictactoe")


def _extra(parser: argparse.ArgumentParser) -> None:
    """``create [game type] [moniker]``: both optional, prompted when absent."""
    parser.add_argument("game_type", nargs="?", choices=GAME_TYPES, default=None,
                        help="game type for create (prompted if omitted)")
    parser.add_argument("moniker", nargs="?", default=None,
                        help="table moniker for create (prompted if omitted)")


def _echo_error(message):
    """Report an ambiguous subcommand through this package's own ``io``."""
    io.echo(message, level="error")


def _resolve_subcommand(input_str):
    """Resolve a typed subcommand against this package's SUBCOMMANDS. See ``_common``."""
    return _common.resolve_subcommand(input_str, SUBCOMMANDS, report=_echo_error)


def init(args, **kw) -> bool:
    return _common.register(
        name="casino.table",
        module_path="casino.commands.table",
        version=__version__,
    )


def access(args, op: str, **kw) -> bool:
    """Table ops need an authenticated player. ``update_table`` is also open to a
    table owner. The server enforces ownership when the command runs; this gate only
    decides whether the menu shows it. The client is passed as ``client``.
    """
    client = kw.get("client")
    if client is None or not getattr(client, "authenticated", False):
        return False
    if op == "update_table":
        return bool(getattr(client, "is_sysop", False) or getattr(client, "owns_tables", False))
    return True


def version(args, **kw) -> str:
    return __version__


def buildargs(args, **kw):
    return _common.build_parser("table", subcommands=SUBCOMMANDS, extra=_extra)


def main(args, **kw) -> bool:
    return _common.dispatch(
        args,
        SUBCOMMANDS,
        menu=lib.menu,
        version_text=__version__,
        name="table",
        **kw,
    )
