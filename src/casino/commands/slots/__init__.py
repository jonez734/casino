# commands/slots/__init__.py
# Slots commands: spin, play, paytable, and history.

from bbsengine6 import io

from casino.commands import _common

from . import lib

__version__ = "202608161200"

SUBCOMMANDS = {
    "spin": lib.slot_spin,
    "play": lib.play,
    "paytable": lib.slot_paytable,
    "history": lib.slot_history,
}


def _echo_error(message):
    """Report an ambiguous subcommand through this package's own ``io``."""
    io.echo(message, level="error")


def _resolve_subcommand(input_str):
    """Resolve a typed subcommand against this package's SUBCOMMANDS. See ``_common``."""
    return _common.resolve_subcommand(input_str, SUBCOMMANDS, report=_echo_error)


def init(args, **kw) -> bool:
    return _common.register(
        name="casino.slots",
        module_path="casino.commands.slots",
        version=__version__,
    )


def access(args, op: str, **kw) -> bool:
    return True


def version(args, **kw) -> str:
    return __version__


def buildargs(args, **kw):
    return _common.build_parser("slots", subcommands=SUBCOMMANDS)


def main(args, **kw) -> bool:
    return _common.dispatch(
        args,
        SUBCOMMANDS,
        menu=lib.menu,
        version_text=__version__,
        name="slots",
        **kw,
    )
