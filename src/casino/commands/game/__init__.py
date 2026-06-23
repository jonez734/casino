# commands/game/__init__.py
# Game commands module

from bbsengine6 import io, register_module

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


def _resolve_subcommand(input_str: str) -> str | None:
    """Resolve subcommand input, handling ambiguous matches.

    Args:
        input_str: Subcommand string to resolve

    Returns:
        Resolved subcommand name if unambiguous, None if no match,
        Prints error if ambiguous
    """
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
        name="casino.game",
        module_path="casino.commands.game",
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
