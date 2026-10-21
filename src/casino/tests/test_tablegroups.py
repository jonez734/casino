"""casino.tablegroups: table message groups derived from seating.

bbsengine6's group and source calls are mocked. These tests pin the rules:
naming, which roles are members, last-leave deletion, table deletion, and
reconcile against seats.
"""

from __future__ import annotations

import sys

import pytest
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from casino import tablegroups as tg  # noqa: E402

pytestmark = pytest.mark.tablegroups_real


class TestNaming(unittest.TestCase):
    def test_group_name(self):
        self.assertEqual(tg.table_group_name("jam"), "table:jam")

    def test_dealer_source(self):
        self.assertEqual(tg.dealer_source("jam"), "casino.dealer:jam")


class TestSeatRules(unittest.TestCase):
    @patch("casino.tablegroups._msg")
    def test_player_seat_adds_member(self, msg):
        tg.on_seat("jam", "alice", role="player")
        msg.group_member_add.assert_called_once_with("table:jam", "alice")

    @patch("casino.tablegroups._msg")
    def test_player_dealer_is_a_member(self, msg):
        tg.on_seat("jam", "dana", role="dealer")
        msg.group_member_add.assert_called_once()

    @patch("casino.tablegroups._msg")
    def test_spectator_is_never_a_member(self, msg):
        tg.on_seat("jam", "sam", role="spectator")
        msg.group_member_add.assert_not_called()

    @patch("casino.tablegroups._msg")
    def test_unseat_removes_member(self, msg):
        tg.on_unseat("jam", "alice")
        msg.group_member_remove.assert_called_once_with("table:jam", "alice")


class TestLifecycle(unittest.TestCase):
    @patch("casino.tablegroups._msg")
    def test_create_makes_group_and_registers_dealer_source(self, msg):
        tg.on_table_created("jam", owner_moniker="owner")
        msg.ensure_message_group.assert_called_once()
        msg.register_named_source.assert_called_once_with(
            "casino.dealer:jam", "table:jam", description="bot dealer for jam"
        )

    @patch("casino.tablegroups._msg")
    def test_delete_removes_group_and_source(self, msg):
        tg.on_table_deleted("jam")
        msg.group_delete.assert_called_once_with("table:jam")
        msg.unregister_named_source.assert_called_once_with("casino.dealer:jam")


class TestReconcile(unittest.TestCase):
    @patch("casino.tablegroups._msg")
    def test_stale_member_removed_and_missing_added(self, msg):
        msg.group_member_monikers.return_value = ["alice", "ghost"]
        msg.group_names_with_prefix.return_value = []
        tg.reconcile(
            seats=[("jam", "alice", "player"), ("jam", "dana", "dealer"), ("jam", "sam", "spectator")],
            table_monikers=["jam"],
        )
        msg.group_member_remove.assert_called_once_with("table:jam", "ghost")
        added = {c.args[1] for c in msg.group_member_add.call_args_list}
        self.assertEqual(added, {"dana"})  # alice already present; sam is a spectator

    @patch("casino.tablegroups._msg")
    def test_group_for_deleted_table_is_removed(self, msg):
        msg.group_names_with_prefix.return_value = ["table:gone", "table:jam"]
        msg.group_member_monikers.return_value = []
        tg.reconcile(seats=[], table_monikers=["jam"])
        msg.group_delete.assert_any_call("table:gone")
        msg.unregister_named_source.assert_any_call("casino.dealer:gone")

    @patch("casino.tablegroups._msg")
    def test_live_table_group_not_deleted(self, msg):
        msg.group_names_with_prefix.return_value = ["table:jam"]
        msg.group_member_monikers.return_value = []
        tg.reconcile(seats=[], table_monikers=["jam"])
        for c in msg.group_delete.call_args_list:
            self.assertNotEqual(c, call("table:jam"))


if __name__ == "__main__":
    unittest.main()
