"""A leave does not wait for the table's message-group cleanup.

The seat row is removed first and is the source of truth. The group cleanup is derived from it and best-effort, so
it must not hold up the leave: a slow or refused group database connection stalled the reply past the client's
timeout ("No reply to leave"). The cleanup is handed off, and the leave returns at once.
"""

import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from casino.services import table as table_mod


pytestmark = pytest.mark.unit


def test_a_leave_returns_without_waiting_for_a_blocked_group_cleanup():
    svc = table_mod.TableService.__new__(table_mod.TableService)
    svc.args = SimpleNamespace()
    svc._pool = None
    release = threading.Event()

    def blocked_group_remove(name, player):
        release.wait(timeout=5)  # stands in for a group database connection that is not available

    from casino import tablegroups as tg

    with patch.object(table_mod.dal_table, "remove_player_from_table", return_value=True), \
         patch.object(tg._msg, "group_member_remove", side_effect=blocked_group_remove):
        start = time.monotonic()
        result = svc.leave_table("blackjack-jam", "jam")
        elapsed = time.monotonic() - start
    release.set()

    assert result["success"] is True
    assert elapsed < 1.0, f"the leave waited {elapsed:.1f}s for the group cleanup"
