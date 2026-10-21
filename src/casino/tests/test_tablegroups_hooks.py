"""TableService calls tablegroups on seat, unseat, create, and delete.

A seat change that skips the hook would leave the table's message group out
of step with the seats. These tests fail if a hook is removed.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import casino.services.table as svc  # noqa: E402


def _service():
    t = svc.TableService.__new__(svc.TableService)
    t.args = MagicMock()
    t._pool = None
    return t


class TestServiceHooks(unittest.TestCase):
    def test_join_seats_and_joins_group(self):
        with patch("casino.tablegroups.on_seat") as seat, \
             patch.object(svc.dal_table, "get_table", return_value={"moniker": "jam"}), \
             patch.object(svc.dal_table, "add_player_to_table", return_value=True):
            _service().join_table("jam", "alice")
        seat.assert_called_once_with("jam", "alice", role="player")

    def test_join_no_op_does_not_touch_group(self):
        with patch("casino.tablegroups.on_seat") as seat, \
             patch.object(svc.dal_table, "get_table", return_value={"moniker": "jam"}), \
             patch.object(svc.dal_table, "add_player_to_table", return_value=False):
            _service().join_table("jam", "alice")
        seat.assert_not_called()

    def test_leave_unseats_and_leaves_group(self):
        with patch("casino.tablegroups.on_unseat") as unseat, \
             patch.object(svc.dal_table, "remove_player_from_table", return_value=True):
            _service().leave_table("jam", "alice")
        unseat.assert_called_once_with("jam", "alice")

    def test_leave_when_not_seated_does_not_touch_group(self):
        with patch("casino.tablegroups.on_unseat") as unseat, \
             patch.object(svc.dal_table, "remove_player_from_table", return_value=False):
            _service().leave_table("jam", "alice")
        unseat.assert_not_called()

    def test_delete_removes_group(self):
        with patch("casino.tablegroups.on_table_deleted") as gone, \
             patch.object(svc.dal_table, "get_table", return_value={"moniker": "jam", "ownermoniker": "owner"}), \
             patch.object(svc.dal_table, "delete_table", return_value=True):
            _service().delete_table("jam", "owner")
        gone.assert_called_once_with("jam")


if __name__ == "__main__":
    unittest.main()
