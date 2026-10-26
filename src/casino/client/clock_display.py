"""Countdown display for the play clock (Phase 1c).

The server owns the deadline. A table's ``action_deadline`` is an ISO timestamp set by the server;
the client shows the seconds left from it. Seconds are computed against the client's clock, so a
badly set client clock only shifts the display, never the outcome: the server decides expiry.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def parse_deadline(value) -> Optional[datetime]:
    """The server's deadline as an aware datetime, or None when no clock is running."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def seconds_left(deadline: Optional[datetime], *, now: Optional[datetime] = None) -> Optional[int]:
    """Whole seconds until the deadline, never negative; None when no clock is running."""
    if deadline is None:
        return None
    current = now or datetime.now(timezone.utc)
    return max(0, int((deadline - current).total_seconds()))


def countdown_text(value, *, now: Optional[datetime] = None) -> str:
    """The countdown for a table, e.g. 'clock 17s', or '' when no clock is running."""
    left = seconds_left(parse_deadline(value), now=now)
    if left is None:
        return ""
    return f"clock {left}s"
