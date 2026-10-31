# commands/admin/__init__.py
# Admin commands: watch, unwatch, and kick (sysop only).

from bbsengine6 import io

from casino.commands import _common

from . import lib

__version__ = "202210010112"

SUBCOMMANDS = {
    "watch": lib.watch_table,
    "unwatch": lib.unwatch_table,
    "kick": lib.kick_player,
}


def _echo_error(message):
    """Report an ambiguous subcommand through this package's own ``io``."""
    io.echo(message, level="error")


def _resolve_subcommand(input_str):
    """Resolve a typed subcommand against this package's SUBCOMMANDS. See ``_common``."""
    return _common.resolve_subcommand(input_str, SUBCOMMANDS, report=_echo_error)


def init(args, **kw) -> bool:
    return _common.register(
        name="casino.admin",
        module_path="casino.commands.admin",
        version=__version__,
    )


_SYSOP_OPS = {"watch_table", "stop_watching", "kick_player"}


def access(args, op: str, **kw) -> bool:
    """Admin ops are sysop-only. The client is passed as ``client`` by the menu gate."""
    client = kw.get("client")
    if client is None or not getattr(client, "authenticated", False):
        return False
    return bool(getattr(client, "is_sysop", False)) if op in _SYSOP_OPS else True


def version(args, **kw) -> str:
    return __version__


def buildargs(args, **kw):
    return _common.build_parser("admin", subcommands=SUBCOMMANDS)


def main(args, **kw) -> bool:
    return _common.dispatch(
        args,
        SUBCOMMANDS,
        menu=lib.menu,
        version_text=__version__,
        name="admin",
        **kw,
    )
