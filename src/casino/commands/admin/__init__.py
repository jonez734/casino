# commands/admin/__init__.py
# Admin commands module

import argparse

from bbsengine6 import io, register_module

from . import lib

__version__ = "202210010112"

SUBCOMMANDS = {
    "watch": lib.watch_table,
    "unwatch": lib.unwatch_table,
    "kick": lib.kick_player,
    # Future security commands (not yet implemented):
    # "ban": lib.ban_player,
    # "unban": lib.unban_player,
    # "disconnect": lib.disconnect_player,
    # "connections": lib.show_connections,
}


def _resolve_subcommand(input_str: str) -> str | None:
    """Resolve subcommand input, handling ambiguous matches."""
    if not input_str:
        return None

    input_lower = input_str.lower()
    matches = [name for name in SUBCOMMANDS if name.startswith(input_lower)]

    if len(matches) == 0:
        return None
    if len(matches) == 1:
        return matches[0]

    io.echo(f"Ambiguous: '{input_str}' could be {', '.join(matches)}", level="error")
    return None


def init(args, **kw) -> bool:
    register_module(
        name="casino.admin",
        module_path="casino.commands.admin",
        version=__version__,
        apis={},
    )
    return True


def access(args, op: str, **kw) -> bool:
    return True


def buildargs(args, **kwargs):
    parser = argparse.ArgumentParser()
    parser.add_argument("tables", nargs="?", default=None, help="Table moniker(s) or 'all'")
    parser.add_argument("player", nargs="?", default=None, help="Player to kick")
    return parser


def main(args, **kw) -> bool:
    subcommand = kw.get("subcommand")

    if subcommand is None:
        lib.menu(args, **kw)
    else:
        resolved = _resolve_subcommand(subcommand)
        if resolved:
            SUBCOMMANDS[resolved](args, **kw)
        else:
            io.echo(f"Unknown subcommand: {subcommand}", level="error")
            lib.menu(args, **kw)

    return True
