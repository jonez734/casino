"""Message groups for casino tables, derived from seating.

Every game with a table gets a message group named ``table:<moniker>``. A
member is in the group exactly while they hold a seat at the table
(``casino.map_cardtable_player`` with role ``player`` or ``dealer``).
Spectators are never members.

A table's dealer, when it is a bot, is a virtual sender. It posts as the named
source ``casino.dealer:<moniker>``, which is registered for the prefix
``table:<moniker>`` when the table is created and removed when it is deleted.

All games call this module; no game builds group names itself. Seat writes
call :func:`on_seat` / :func:`on_unseat` only after the seat row is written.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Iterable, TypeVar

from bbsengine6.message import service as _msg

logger = logging.getLogger(__name__)
_T = TypeVar("_T")

GROUP_PREFIX = "table"
DEALER_SOURCE_PREFIX = "casino.dealer"
SEATED_ROLES = frozenset({"player", "dealer"})


def _best_effort(fn: Callable[[], _T], what: str) -> _T | None:
    """Run a group side effect without letting it break the table operation.

    The seat row is the source of truth; the group is derived from it. A
    failed group update is logged and corrected by :func:`reconcile` at the
    next startup, rather than failing the seat or table change.
    """
    try:
        return fn()
    except Exception:
        logger.exception("tablegroups: %s failed", what)
        return None


def table_group_name(table_moniker: str) -> str:
    """The message group for a table, e.g. ``table:jam``."""
    return f"{GROUP_PREFIX}:{table_moniker}"


def dealer_source(table_moniker: str) -> str:
    """The named message source a bot dealer posts as, e.g. ``casino.dealer:jam``."""
    return f"{DEALER_SOURCE_PREFIX}:{table_moniker}"


def on_table_created(table_moniker: str, owner_moniker: str | None = None) -> None:
    """Create the table's group and register its bot dealer source."""
    _best_effort(
        lambda: _msg.ensure_message_group(
            table_group_name(table_moniker),
            description=f"seated players at {table_moniker}",
        ),
        "create group",
    )
    _best_effort(
        lambda: _msg.register_named_source(
            dealer_source(table_moniker),
            table_group_name(table_moniker),
            description=f"bot dealer for {table_moniker}",
        ),
        "register dealer source",
    )


def on_seat(table_moniker: str, player_moniker: str, role: str = "player") -> None:
    """Add a newly seated member to the table's group. Spectators are ignored."""
    if role not in SEATED_ROLES:
        return
    _best_effort(
        lambda: _msg.group_member_add(table_group_name(table_moniker), player_moniker),
        "add member",
    )


def on_unseat(table_moniker: str, player_moniker: str) -> None:
    """Remove a member from the table's group. The group is deleted when empty."""
    _best_effort(
        lambda: _msg.group_member_remove(table_group_name(table_moniker), player_moniker),
        "remove member",
    )


def on_table_deleted(table_moniker: str) -> None:
    """Delete the table's group and unregister its bot dealer source."""
    _best_effort(lambda: _msg.group_delete(table_group_name(table_moniker)), "delete group")
    _best_effort(
        lambda: _msg.unregister_named_source(dealer_source(table_moniker)),
        "unregister dealer source",
    )


def reconcile(seats: Iterable[tuple[str, str, str]], table_monikers: Iterable[str]) -> None:
    """Make every table group match the current seated members.

    ``seats`` yields ``(table_moniker, player_moniker, role)`` for every seat
    row in the database. ``table_monikers`` lists every table that exists.

    - A group for a table that exists is set to exactly its seated members.
    - A ``table:`` group for a table that no longer exists is deleted.

    Runs at startup, so a crash between a seat write and its group update
    cannot leave stale membership.
    """
    wanted: dict[str, set[str]] = {}
    for table, player, role in seats:
        if role in SEATED_ROLES:
            wanted.setdefault(table_group_name(table), set()).add(player)

    live = set(table_monikers)
    for table in live:
        group = table_group_name(table)
        current = set(_msg.group_member_monikers(group))
        target = wanted.get(group, set())
        for stale in current - target:
            _msg.group_member_remove(group, stale)
        for missing in target - current:
            _msg.group_member_add(group, missing, addedby=missing)
        _msg.register_named_source(dealer_source(table), group)

    live_groups = {table_group_name(t) for t in live}
    for group in _msg.group_names_with_prefix(GROUP_PREFIX):
        if group not in live_groups:
            _msg.group_delete(group)
            table = group[len(GROUP_PREFIX) + 1:]
            _msg.unregister_named_source(dealer_source(table))
