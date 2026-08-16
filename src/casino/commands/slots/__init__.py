# commands/slots/__init__.py
# Slots commands module. WS-backed: every subcommand delegates to a
# function in ``lib`` that sends through the connected ``CasinoClient``
# so the bearer token is auto-injected on every wire call. The
# legacy door-mode play loop still lives at ``casino/slots/play.py``
# (reachable via ``casino.slots --door``) but is not wired here.

from bbsengine6 import io, register_module

from . import lib

__version__ = "202608161200"

SUBCOMMANDS = {
    "spin": lib.slot_spin,
    "play": lib.play,
    "paytable": lib.slot_paytable,
    "history": lib.slot_history,
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
        name="casino.slots.commands",
        module_path="casino.commands.slots",
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
