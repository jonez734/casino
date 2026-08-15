#!/usr/bin/env python3
# casino/tests/test_session_manager.py
# Unit tests for CasinoSessionManager and the new spectator_of
# bookkeeping. CasinoSessionManager extends bbsengine6.session.SessionManager
# with per-session table_moniker + spectator_of fields and a reverse
# _spectators index keyed by table_moniker for O(1) observer lookup.

import unittest
from unittest.mock import patch

import sys

sys.path.insert(0, "/home/opencode/data/work/bbsengine6/py/src")


class TestCasinoSessionManager(unittest.TestCase):
    def setUp(self):
        # Silence the io.echo trace so test output stays clean.
        from casino.api.handler import CasinoSessionManager

        self._echo_patcher = patch("casino.api.handler.io.echo")
        self._echo_patcher.start()
        self.sm = CasinoSessionManager()

    def tearDown(self):
        self._echo_patcher.stop()

    def test_register_session_initializes_table_and_spectator(self):
        """register_session seeds table_moniker=None and spectator_of=set()."""
        self.sm.register_session(1, "alice", is_sysop=False)
        session = self.sm.get_session(1)
        self.assertEqual(session["moniker"], "alice")
        self.assertFalse(session["is_sysop"])
        self.assertIsNone(session["table_moniker"])
        self.assertEqual(session["spectator_of"], set())

    def test_register_session_keeps_sysop_flag(self):
        self.sm.register_session(1, "root", is_sysop=True)
        self.assertTrue(self.sm.get_session(1)["is_sysop"])
        self.assertTrue(self.sm.get_is_sysop(1))

    def test_get_table_moniker_unbound_session_returns_none(self):
        self.assertIsNone(self.sm.get_table_moniker(999))

    def test_get_table_moniker_for_seated_player(self):
        self.sm.register_session(1, "alice")
        self.sm.set_table_moniker(1, "room-1")
        self.assertEqual(self.sm.get_table_moniker(1), "room-1")

    def test_set_table_moniker_replaces(self):
        """A player can only sit at one table at a time."""
        self.sm.register_session(1, "alice")
        self.sm.set_table_moniker(1, "room-1")
        self.sm.set_table_moniker(1, "room-2")
        self.assertEqual(self.sm.get_table_moniker(1), "room-2")

    def test_set_table_moniker_to_none_clears(self):
        self.sm.register_session(1, "alice")
        self.sm.set_table_moniker(1, "room-1")
        self.sm.set_table_moniker(1, None)
        self.assertIsNone(self.sm.get_table_moniker(1))

    def test_set_table_moniker_unknown_session_is_noop(self):
        """Setting on an unbound session must not raise."""
        self.sm.set_table_moniker(999, "room-1")
        self.assertIsNone(self.sm.get_table_moniker(999))

    def test_add_spectator_adds_to_session_and_index(self):
        self.sm.register_session(1, "alice")
        self.sm.add_spectator("room-1", 1)
        self.assertEqual(self.sm.get_session(1)["spectator_of"], {"room-1"})
        self.assertEqual(self.sm.get_table_observers("room-1"), {1})

    def test_add_spectator_multi_table(self):
        """A session can spectate multiple tables concurrently."""
        self.sm.register_session(1, "alice")
        self.sm.add_spectator("room-1", 1)
        self.sm.add_spectator("room-2", 1)
        self.assertEqual(
            self.sm.get_session(1)["spectator_of"], {"room-1", "room-2"}
        )
        self.assertEqual(self.sm.get_table_observers("room-1"), {1})
        self.assertEqual(self.sm.get_table_observers("room-2"), {1})

    def test_add_spectator_multi_session(self):
        self.sm.register_session(1, "alice")
        self.sm.register_session(2, "bob")
        self.sm.add_spectator("room-1", 1)
        self.sm.add_spectator("room-1", 2)
        self.assertEqual(self.sm.get_table_observers("room-1"), {1, 2})

    def test_add_spectator_idempotent(self):
        self.sm.register_session(1, "alice")
        self.sm.add_spectator("room-1", 1)
        self.sm.add_spectator("room-1", 1)
        self.assertEqual(self.sm.get_table_observers("room-1"), {1})

    def test_remove_spectator_clears_index_and_session(self):
        self.sm.register_session(1, "alice")
        self.sm.add_spectator("room-1", 1)
        self.sm.remove_spectator("room-1", 1)
        self.assertEqual(self.sm.get_session(1)["spectator_of"], set())
        self.assertEqual(self.sm.get_table_observers("room-1"), set())

    def test_remove_spectator_keeps_other_tables(self):
        """Removing one watched table leaves other watches intact."""
        self.sm.register_session(1, "alice")
        self.sm.add_spectator("room-1", 1)
        self.sm.add_spectator("room-2", 1)
        self.sm.remove_spectator("room-1", 1)
        self.assertEqual(self.sm.get_session(1)["spectator_of"], {"room-2"})
        self.assertEqual(self.sm.get_table_observers("room-2"), {1})

    def test_remove_spectator_idempotent(self):
        """Removing a non-watched table is a no-op (does not crash)."""
        self.sm.register_session(1, "alice")
        self.sm.remove_spectator("room-1", 1)
        self.assertEqual(self.sm.get_session(1)["spectator_of"], set())
        self.assertEqual(self.sm.get_table_observers("room-1"), set())

    def test_get_table_player_count_counts_seated_only(self):
        """Spectators do not count toward player count."""
        self.sm.register_session(1, "alice")
        self.sm.register_session(2, "bob")
        self.sm.register_session(3, "carol")
        self.sm.set_table_moniker(1, "room-1")
        self.sm.set_table_moniker(2, "room-1")
        self.sm.add_spectator("room-1", 3)
        self.assertEqual(self.sm.get_table_player_count("room-1"), 2)

    def test_get_table_player_count_zero_for_unknown(self):
        self.assertEqual(self.sm.get_table_player_count("nope"), 0)

    def test_unregister_session_purges_spectator_index(self):
        """Disconnecting a spectator removes them from every watched table."""
        self.sm.register_session(1, "alice")
        self.sm.add_spectator("room-1", 1)
        self.sm.add_spectator("room-2", 1)
        self.sm.unregister_session(1)
        self.assertEqual(self.sm.get_table_observers("room-1"), set())
        self.assertEqual(self.sm.get_table_observers("room-2"), set())
        self.assertIsNone(self.sm.get_session(1))

    def test_unregister_session_preserves_other_spectators(self):
        """Disconnecting one spectator must not evict another."""
        self.sm.register_session(1, "alice")
        self.sm.register_session(2, "bob")
        self.sm.add_spectator("room-1", 1)
        self.sm.add_spectator("room-1", 2)
        self.sm.unregister_session(1)
        self.assertEqual(self.sm.get_table_observers("room-1"), {2})

    def test_unregister_unknown_session_is_noop(self):
        self.sm.unregister_session(999)
        # No exception.

    def test_get_table_observers_empty_for_unwatched_table(self):
        self.assertEqual(self.sm.get_table_observers("nope"), set())


if __name__ == "__main__":
    unittest.main()
