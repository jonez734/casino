"""Per-seat play clock for poker (Phase 1b).

Poker is turn-based: ``PokerTableState.current_player`` holds the one seat to act. The clock
belongs to that seat. When the turn passes to a human seat, a deadline is set from the table's
turn_seconds (0 = off). If it passes before the seat acts, the penalty applies to that seat only:

- ``skip``: the seat checks if it can; otherwise it folds. The engine never bets for the player.
- ``remove``: the seat folds out of the hand.

Bots are never clocked. The table is not paused by another seat's clock. Every expiry is logged.
Expiry is applied by the engine before any action is accepted, so a late action cannot beat it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

PENALTIES = frozenset({"skip", "remove"})


def deadline_for(turn_seconds: int, *, now: Optional[datetime] = None) -> Optional[datetime]:
    """Deadline for a seat that has just been given the turn, or None when the clock is off."""
    if not turn_seconds or turn_seconds <= 0:
        return None
    base = now or datetime.now(timezone.utc)
    return base + timedelta(seconds=int(turn_seconds))


def is_expired(deadline: Optional[datetime], *, now: Optional[datetime] = None) -> bool:
    """True when a deadline is set and has passed."""
    if deadline is None:
        return False
    return (now or datetime.now(timezone.utc)) >= deadline


def penalty_for(clock_penalty: Optional[str]) -> str:
    """The penalty name, with skip as the default for anything unknown."""
    return clock_penalty if clock_penalty in PENALTIES else "skip"


def clocked(seat: Any) -> bool:
    """A seat is clocked only when it is human. Bots are never clocked."""
    return not getattr(seat, "is_bot", False)


def apply_expiry(table: Any, seat: Any, *, facing_bet: bool) -> dict[str, Any]:
    """Apply the penalty to one seat whose turn expired. Returns the action taken.

    ``facing_bet`` is true when the seat owes chips to call. A skip checks when it can and folds
    when it cannot. A remove always folds the seat out.
    """
    penalty = penalty_for(getattr(table, "clock_penalty", "skip"))
    if penalty == "remove" or facing_bet:
        seat.has_folded = True
        seat.showing_cards = False
        action = "fold"
    else:
        seat.has_acted = True
        action = "check"
    return {"penalty": penalty, "action": action, "seat": seat.moniker}
