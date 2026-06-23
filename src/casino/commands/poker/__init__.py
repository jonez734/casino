# commands/poker/__init__.py
# Poker commands module

from bbsengine6 import io, register_module

from . import lib

__version__ = "202406010000"

SUBCOMMANDS = {
    "check": lib.check,
    "call": lib.call,
    "bet": lib.bet,
    "raise": lib.raise_bet,
    "fold": lib.fold,
    "allin": lib.all_in,
    "show": lib.show_hand,
    "muck": lib.muck_hand,
    "hand": lib.show_my_hand,
    "table": lib.show_table,
    "players": lib.list_players,
    "deck": lib.show_deck,
    "create": lib.create_table,
    "join": lib.join_table,
    "leave": lib.leave_table,
    "list": lib.list_tables,
    "start": lib.start_hand,
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
        name="casino.poker.commands",
        module_path="casino.commands.poker",
        version=__version__,
        apis={},
    )
    return True


def access(args, op: str, **kw) -> bool:
    return True


def buildargs(args, **kw):
    return None


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
