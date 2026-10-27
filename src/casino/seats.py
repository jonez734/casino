"""Seat modules: one registry for how many seats a game table holds (Phase 4, slice 1).

Each game type declares its seats here. A seat module is the game's rule for capacity; the table
row does not carry it. Callers read capacity through :func:`seat_module` so the join path, the
clock, and the lobby all agree on one number.

Slice 1 only declares the rules. Enforcement and bots come in later slices.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SeatModule:
    """The seat rule for one game type.

    ``min_players`` is the floor the table needs before a hand can start. ``max_players`` is the
    most seats a table can hold. Spectators do not count against either.
    """

    game_type: str
    min_players: int
    max_players: int

    def __post_init__(self) -> None:
        if self.min_players < 0 or self.max_players < 0:
            raise ValueError(f"{self.game_type}: seat counts cannot be negative")
        if self.min_players > self.max_players:
            raise ValueError(
                f"{self.game_type}: min_players {self.min_players} exceeds max_players {self.max_players}"
            )


# One entry per game type. The values follow the "Seats per Table" design (TODO.md).
_MODULES: dict[str, SeatModule] = {
    "blackjack": SeatModule("blackjack", min_players=1, max_players=7),
    "poker": SeatModule("poker", min_players=2, max_players=10),
    "slots": SeatModule("slots", min_players=0, max_players=1),
    "yahtzee": SeatModule("yahtzee", min_players=1, max_players=6),
    "tictactoe": SeatModule("tictactoe", min_players=2, max_players=2),
}


def seat_module(game_type: str) -> SeatModule | None:
    """The seat module for ``game_type``, or ``None`` when the game has no seat rule."""
    return _MODULES.get(game_type)


def game_types() -> tuple[str, ...]:
    """Every game type that has a seat module, sorted."""
    return tuple(sorted(_MODULES))


def has_room(game_type: str, seated: int) -> bool:
    """True when a table of ``game_type`` with ``seated`` players can take one more.

    An unknown game type has no rule, so the answer is ``True``; enforcement treats that case
    as the caller's concern.
    """
    module = seat_module(game_type)
    if module is None:
        return True
    return seated < module.max_players
