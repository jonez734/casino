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


def _subparsers(parser: argparse.ArgumentParser) -> None:
    """Each subcommand takes its own arguments.

    ``create [game type] [moniker]`` and ``join [moniker]`` take optional
    values; the others take none. A value given on the command line skips its
    prompt. A missing value is prompted for, as before.
    """
    subs = parser.add_subparsers(dest="action", metavar="subcommand")
    create = subs.add_parser("create", add_help=False)
    create.add_argument("game_type", nargs="?", choices=GAME_TYPES, default=None)
    create.add_argument("moniker", nargs="?", default=None)
    join = subs.add_parser("join", add_help=False)
    join.add_argument("moniker", nargs="?", default=None)
    for name in ("list", "update", "leave", "view"):
        subs.add_parser(name, add_help=False)


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
    parser = argparse.ArgumentParser(prog="table", add_help=False)
    parser.add_argument("--version", action="store_true", dest="version")
    _subparsers(parser)
    return parser


def main(args, **kw) -> bool:
    return _common.dispatch(
        args,
        SUBCOMMANDS,
        menu=lib.menu,
        version_text=__version__,
        name="table",
        **kw,
    )
