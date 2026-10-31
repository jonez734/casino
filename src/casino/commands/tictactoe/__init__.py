# commands/tictactoe/__init__.py
# Tic-tac-toe commands: quickplay, move, join, resign. Bed-side only.

from bbsengine6 import io  # noqa: F401  (kept: tests patch io on this package)

from casino.commands import _common

from . import lib

__version__ = "202606261200"

SUBCOMMANDS = {
    "quickplay": lib.quickplay,
    "move": lib.move,
    "join": lib.join,
    "resign": lib.resign,
}


def _echo_error(message):
    """Report an ambiguous subcommand through this package's own ``io``."""
    io.echo(message, level="error")


def _resolve_subcommand(input_str):
    """Resolve a typed subcommand against this package's SUBCOMMANDS. See ``_common``."""
    return _common.resolve_subcommand(input_str, SUBCOMMANDS, report=_echo_error)


def init(args, **kw) -> bool:
    return _common.register(
        name="casino.tictactoe",
        module_path="casino.commands.tictactoe",
        version=__version__,
    )


def access(args, op: str, **kw) -> bool:
    """Tic-tac-toe needs an authenticated player. The menu's ``requires_seated`` gate,
    not this rule, decides whether move, join, and resign are offered at a table."""
    client = kw.get("client")
    if client is None or not getattr(client, "authenticated", False):
        return False
    return True


def version(args, **kw) -> str:
    return __version__


def buildargs(args, **kw):
    return _common.build_parser("tictactoe", subcommands=SUBCOMMANDS)


def main(args, **kw) -> bool:
    return _common.dispatch(
        args,
        SUBCOMMANDS,
        menu=lib.menu,
        version_text=__version__,
        name="tictactoe",
        **kw,
    )
