# casino/services/clock.py
# The reload rule shared by every game clock (blackjack rounds and poker turns).
#
# A bed restart must never end a player's turn. When a game is first read in a new process, the
# clock it stored before the restart is not trusted: it is cleared, and a fresh clock starts from
# the table's turn_seconds. The clock is paused across the restart and resumes at reload, so a
# restart costs no time.

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from casino.services import poker_clock, round_clock


def reload_deadline(turn_seconds: int, *, now: Optional[datetime] = None) -> Optional[datetime]:
    """The deadline a reloaded game gets: a full turn from now, or None when the clock is off."""
    return round_clock.deadline_for(int(turn_seconds or 0), now=now)


def is_expired(deadline: Optional[datetime], *, now: Optional[datetime] = None) -> bool:
    """Shared expiry test. Both clocks use the same definition of "expired"."""
    return round_clock.is_expired(deadline, now=now)


def penalty_for(clock_penalty: Optional[str]) -> str:
    """Shared penalty name, with skip as the default. Poker and blackjack use the same names."""
    return poker_clock.penalty_for(clock_penalty)


def resume_round_clock(game_service: Any, table_moniker: str, game: dict[str, Any]) -> Optional[datetime]:
    """Blackjack: after a restart, restart the round's clock rather than trusting the stored one.

    Called the first time a round is checked in this process. Returns the fresh deadline (also
    stored on the game row), or None when the table's clock is off.
    """
    from casino.dal import game as dal_game
    from casino.dal import table as dal_table

    args = game_service.args
    pool = getattr(game_service, "_pool", None)
    table = dal_table.get_table(args, table_moniker, pool=pool) or {}
    deadline = reload_deadline(table.get("turn_seconds") or 0)
    dal_game.set_action_deadline(args, game["id"], deadline, pool=pool)
    return deadline
