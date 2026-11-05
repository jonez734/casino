# commands/table/play.py
# Play verbs for the seated table, routed by the table's type.
#
# ``table <verb>`` acts on the table the player is seated at. The verb is looked up in the map for that
# table's type, so the same name can mean different things per game (``play`` is blackjack's action; poker
# has ``start`` and ``call`` instead). The seat and the type come from the server's casino_table_state
# push, which the client stores; nothing here guesses them.

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

# The game packages declare their own table verbs (TABLE_VERBS in each package). This module only
# gathers them by table type, so no game's verbs are listed here.
#
# The table type each package serves. Keys are the table's ``type`` value.
_GAME_PACKAGES = {
    "blackjack": "casino.commands.blackjack",
    "poker": "casino.commands.poker",
    "tictactoe": "casino.commands.tictactoe",
}


def _table_verbs() -> dict[str, dict[str, Callable]]:
    """Each table type's verbs and implementations, read from the game packages."""
    import importlib

    return {
        game_type: dict(importlib.import_module(pkg).TABLE_VERBS)
        for game_type, pkg in _GAME_PACKAGES.items()
    }


PLAY_VERBS: dict[str, tuple[str, ...]] = {
    game_type: tuple(verbs) for game_type, verbs in _table_verbs().items()
}


@dataclass(frozen=True)
class Refusal:
    """Why a verb did not run. ``message`` is what the player is told."""

    message: str


def resolve(verb: str, *, seated: bool, game_type: Optional[str]) -> "str | Refusal":
    """Return the verb's game-type key, or a :class:`Refusal` explaining why it cannot run.

    Unseated: ``not seated``. Seated at a type that does not carry the verb: refuse and name the type,
    so a typed verb is never silently accepted or redirected.
    """
    if not seated or not game_type:
        return Refusal("not seated: sit at a table first")
    allowed = PLAY_VERBS.get(game_type)
    if allowed is None:
        return Refusal(f"no play verbs for {game_type} tables")
    if verb not in allowed:
        return Refusal(f"{game_type} has no {verb}")
    return game_type


def verbs_for(game_type: Optional[str]) -> tuple[str, ...]:
    """The verbs a seated player at ``game_type`` can use; empty when not at a table."""
    return PLAY_VERBS.get(game_type or "", ())


def union_of_verbs() -> tuple[str, ...]:
    """Every verb across all table types, in first-seen order. Used to check top-level clashes."""
    seen: list[str] = []
    for verbs in PLAY_VERBS.values():
        for v in verbs:
            if v not in seen:
                seen.append(v)
    return tuple(seen)


def dispatch(verb: str, args, client=None, **kwargs) -> bool:
    """Run ``verb`` against the table the client is seated at, routed by that table's type.

    The seat and type are read from the client (set from the server's casino_table_state push). A
    refusal is reported loudly and returns False; it never runs a different game's verb.
    """
    seated = getattr(client, "current_table_moniker", None) is not None
    game_type = getattr(client, "current_table_game_type", None)
    routed = resolve(verb, seated=seated, game_type=game_type)
    if isinstance(routed, Refusal):
        from bbsengine6 import io

        io.echo(f"{{red}}{routed.message}{{/all}}")
        return False
    return _table_verbs()[routed][verb](args, client=client, **kwargs)
