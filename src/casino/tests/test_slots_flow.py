#!/usr/bin/env python3
# casino/tests/test_slots_flow.py
# Flow-level tests for the slots service: validation, atomic spin, history.

import argparse
import sys
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, "/home/opencode/data/work/casino/src")


class _FakeRow(dict):
    """A dict-like row that supports both key access and dict iteration."""

    def __getitem__(self, k):
        return super().__getitem__(k)


class FakeCursor:
    """Single-cursor fake that the service code reuses across the transaction.

    The slot service opens ONE cursor for the whole transaction and runs
    5 SQL statements on it. The cursor must therefore:
      - return a row from fetchone() for the SELECT FOR UPDATE
      - stash a row for the INSERT ... RETURNING
      - return None for the UPDATEs (no RETURNING)
    """

    def __init__(self, initial_row=None, insert_returning=None):
        self._initial = initial_row
        self._insert_returning = insert_returning
        self.executed = []
        self._stashed = None

    def execute(self, sql, params=None):
        sql_str = str(sql) if sql is not None else ""
        if "INSERT" in sql_str and "RETURNING" in sql_str:
            self._stashed = self._insert_returning
        self.executed.append((sql_str, params))

    def fetchone(self):
        if self._stashed is not None:
            r = self._stashed
            self._stashed = None
            return r
        if self._initial is not None:
            r = self._initial
            self._initial = None
            return r
        return None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False
        self.rolled_back = False

    def cursor(self, *a, **kw):
        return self._cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    @property
    def info(self):
        return {}

    @property
    def closed(self):
        return False


class _StubWebSocket:
    """WebSocket with a stable id() so the session lookup is deterministic."""

    _counter = 0

    def __init__(self):
        # Each instance gets a fresh integer id, unique to that instance.
        type(self)._counter += 1
        self._id = type(self)._counter

    def __hash__(self):
        return self._id

    def __eq__(self, other):
        return isinstance(other, _StubWebSocket) and other._id == self._id


def stable_ws():
    """A websocket object whose id() is stable for the lifetime of the process."""
    return _StubWebSocket()


class TestSlotServiceValidation(unittest.TestCase):
    """Pre-spin validation errors return error codes without touching the DB."""

    def setUp(self):
        self.args = argparse.Namespace(databasename="test", database="test")

    def _patch_db(self, table=None):
        return patch(
            "casino.dal.table.get_table",
            return_value=table,
        )

    def test_invalid_bet_type(self):
        from casino.services.slots import handle_spin

        with self._patch_db(table={"type": "slots", "minimumbet": 1, "maximumbet": 100}):
            r = handle_spin(self.args, "t", "alice", "ten")  # type: ignore[arg-type]
        self.assertFalse(r["success"])
        self.assertEqual(r["code"], "invalid_bet")

    def test_zero_bet(self):
        from casino.services.slots import handle_spin

        with self._patch_db(table={"type": "slots", "minimumbet": 1, "maximumbet": 100}):
            r = handle_spin(self.args, "t", "alice", 0)
        self.assertFalse(r["success"])
        self.assertEqual(r["code"], "invalid_bet")

    def test_table_not_found(self):
        from casino.services.slots import handle_spin

        with self._patch_db(table=None):
            r = handle_spin(self.args, "missing", "alice", 10)
        self.assertFalse(r["success"])
        self.assertEqual(r["code"], "table_not_found")

    def test_wrong_game_type(self):
        from casino.services.slots import handle_spin

        with self._patch_db(table={"type": "blackjack", "minimumbet": 1, "maximumbet": 100}):
            r = handle_spin(self.args, "t", "alice", 10)
        self.assertFalse(r["success"])
        self.assertEqual(r["code"], "wrong_game_type")

    def test_bet_below_min(self):
        from casino.services.slots import handle_spin

        with self._patch_db(table={"type": "slots", "minimumbet": 5, "maximumbet": 100}):
            r = handle_spin(self.args, "t", "alice", 1)
        self.assertFalse(r["success"])
        self.assertEqual(r["code"], "bet_below_min")

    def test_bet_above_max(self):
        from casino.services.slots import handle_spin

        with self._patch_db(table={"type": "slots", "minimumbet": 1, "maximumbet": 100}):
            r = handle_spin(self.args, "t", "alice", 500)
        self.assertFalse(r["success"])
        self.assertEqual(r["code"], "bet_above_max")


class TestSlotServiceSpinSuccess(unittest.TestCase):
    """Happy path: atomic transaction debits, records, and credits stats."""

    def setUp(self):
        self.args = argparse.Namespace(databasename="test", database="test")

    def test_successful_spin_writes_audit_and_bumps_stats(self):
        from casino.services.slots import handle_spin, _dealers, invalidate_dealer

        # Build a dealer that always produces a winning 3-of-a-kind SEVEN
        class StubDealer:
            num_reels = 5
            num_rows = 3
            def play(self, bet):
                from casino.slots.lib import Symbol, SpinResult, Win
                seven = Symbol("SEVEN", 1, "7")
                return SpinResult(
                    reels=[[seven] * 3 for _ in range(5)],
                    center_row=[seven] * 5,
                    wins=[Win(("SEVEN",) * 3, 145, bet * 145)],
                    bet=bet,
                    payout=bet * 145,
                    net=bet * 145 - bet,
                )

        # Force the dealer cache to a deterministic stub
        _dealers["slots-test"] = StubDealer()
        self.addCleanup(invalidate_dealer, "slots-test")

        # The service uses ONE cursor for the whole transaction:
        #   1) SELECT FOR UPDATE -> returns {"id":1, "balance":100}
        #   2) UPDATE balance (no return)
        #   3) INSERT spin RETURNING id -> returns {"id": 42}
        #   4) UPDATE stats (no return)
        #   5) UPDATE biggest_win (no return)
        cursor = FakeCursor(
            initial_row={"id": 1, "balance": 100},
            insert_returning={"id": 42},
        )
        conn = FakeConn(cursor)
        from contextlib import contextmanager

        @contextmanager
        def fake_connect(*a, **kw):
            yield conn

        with patch("casino.services.slots.database.connect", fake_connect), \
             patch("casino.services.slots.database.cursor",
                   side_effect=lambda c, **kw: c.cursor()), \
             patch("casino.dal.table.get_table",
                   return_value={"type": "slots", "minimumbet": 1, "maximumbet": 100}):
            r = handle_spin(self.args, "slots-test", "alice", 10)

        self.assertTrue(r["success"], msg=f"got: {r}")
        self.assertEqual(r["spin"]["id"], 42)
        self.assertEqual(r["spin"]["bet"], 10)
        self.assertEqual(r["spin"]["payout"], 1450)
        self.assertEqual(r["spin"]["net"], 1440)
        self.assertEqual(r["spin"]["new_balance"], 100 + 1440)
        # 5 SQL statements: SELECT, UPDATE, INSERT, UPDATE, UPDATE
        self.assertEqual(len(cursor.executed), 5)

    def test_insufficient_funds_rolls_back(self):
        from casino.services.slots import handle_spin, _dealers, invalidate_dealer

        class StubDealer:
            num_reels = 5
            num_rows = 3
            def play(self, bet):
                from casino.slots.lib import Symbol, SpinResult
                lemon = Symbol("LEMON", 1, "l")
                return SpinResult(
                    reels=[[lemon] * 3 for _ in range(5)],
                    center_row=[lemon] * 5,
                    wins=[],
                    bet=bet,
                    payout=0,
                    net=-bet,
                )

        _dealers["slots-test"] = StubDealer()
        self.addCleanup(invalidate_dealer, "slots-test")

        # account exists but balance is 1, bet is 10 -> insufficient_funds
        cursor = FakeCursor(initial_row={"id": 1, "balance": 1})
        conn = FakeConn(cursor)
        from contextlib import contextmanager

        @contextmanager
        def fake_connect(*a, **kw):
            yield conn

        with patch("casino.services.slots.database.connect", fake_connect), \
             patch("casino.services.slots.database.cursor",
                   side_effect=lambda c, **kw: c.cursor()), \
             patch("casino.dal.table.get_table",
                   return_value={"type": "slots", "minimumbet": 1, "maximumbet": 100}):
            r = handle_spin(self.args, "slots-test", "alice", 10)

        self.assertFalse(r["success"])
        self.assertEqual(r["code"], "insufficient_funds")


class TestSlotPaytableLookup(unittest.TestCase):
    def setUp(self):
        self.args = argparse.Namespace(databasename="test", database="test")

    def test_paytable_lookup(self):
        from casino.services.slots import handle_get_paytable, _dealers, invalidate_dealer
        from casino.slots.lib import Paytable

        _dealers["slots-test"] = type("D", (), {
            "num_reels": 5, "num_rows": 3,
            "play": lambda self, bet: None,
            "paytable": Paytable(),
        })()
        self.addCleanup(invalidate_dealer, "slots-test")

        with patch("casino.dal.table.get_table", return_value={"type": "slots"}):
            r = handle_get_paytable(self.args, "slots-test")

        self.assertTrue(r["success"])
        self.assertEqual(r["moniker"], "slots-test")
        self.assertGreater(len(r["payouts"]), 0)
        # Each entry has symbols and multiplier
        for entry in r["payouts"]:
            self.assertIn("symbols", entry)
            self.assertIn("multiplier", entry)

    def test_paytable_wrong_game_type(self):
        from casino.services.slots import handle_get_paytable

        with patch("casino.dal.table.get_table", return_value={"type": "blackjack"}):
            r = handle_get_paytable(self.args, "bj-table")
        self.assertFalse(r["success"])
        self.assertEqual(r["code"], "wrong_game_type")

    def test_paytable_table_not_found(self):
        from casino.services.slots import handle_get_paytable

        with patch("casino.dal.table.get_table", return_value=None):
            r = handle_get_paytable(self.args, "missing")
        self.assertFalse(r["success"])
        self.assertEqual(r["code"], "table_not_found")


class TestSlotServiceHandler(unittest.TestCase):
    """Verify the WebSocket handler dispatches and constructs the right replies."""

    def setUp(self):
        from casino.api.handler import SlotServiceHandler, SessionManager

        self.args = argparse.Namespace(databasename="test", database="test")
        self.sessions = SessionManager()
        self.handler = SlotServiceHandler(self.args, self.sessions, channel_state=None)
        # Use a stable WS object and register its id() as session 1
        self.ws = stable_ws()
        self.sessions.register_session(id(self.ws), "alice", is_sysop=False)

    def test_dispatches_unknown_type_to_none(self):
        import asyncio
        r = asyncio.run(self.handler.handle_message(None, self.ws, "/", {"type": "noop"}))
        self.assertIsNone(r)

    def test_slot_spin_no_table(self):
        import asyncio
        r = asyncio.run(self.handler.handle_message(
            None, self.ws, "/", {"type": "slot_spin", "bet": 10}
        ))
        self.assertEqual(r["code"], "not_at_table")

    def test_slot_paytable_no_table(self):
        import asyncio
        r = asyncio.run(self.handler.handle_message(
            None, self.ws, "/", {"type": "slot_paytable"}
        ))
        self.assertEqual(r["code"], "not_at_table")

    def test_slot_history_no_auth(self):
        import asyncio
        from casino.api.handler import SessionManager, SlotServiceHandler
        sessions = SessionManager()
        handler = SlotServiceHandler(self.args, sessions, channel_state=None)
        other_ws = stable_ws()
        r = asyncio.run(handler.handle_message(
            None, other_ws, "/", {"type": "slot_history"}
        ))
        self.assertEqual(r["code"], "not_authenticated")

    def test_slot_history_with_auth(self):
        import asyncio
        with patch("casino.services.slots.dal_slots.get_spin_history", return_value=[]):
            r = asyncio.run(self.handler.handle_message(
                None, self.ws, "/", {"type": "slot_history", "limit": 10}
            ))
        self.assertEqual(r["type"], "slot_history")
        self.assertEqual(r["spins"], [])


class TestSlotServiceHandlerSpinBroadcast(unittest.TestCase):
    """Verify a successful spin publishes to the table channel."""

    def setUp(self):
        from casino.api.handler import SlotServiceHandler, SessionManager

        self.args = argparse.Namespace(databasename="test", database="test")
        self.sessions = SessionManager()
        self.handler = SlotServiceHandler(self.args, self.sessions, channel_state=None)
        self.ws = stable_ws()
        self.sessions.register_session(id(self.ws), "alice", is_sysop=False)
        self.sessions.set_table_moniker(id(self.ws), "slots-test")
        # Patch the underlying handle_spin to return success
        self._patcher = patch.object(
            self.handler, "_handle_spin",
            return_value={
                "success": True,
                "spin": {
                    "id": 7, "bet": 10, "payout": 0, "net": -10,
                    "reels": [], "center_row": [], "wins": [],
                },
            },
        )
        self._patcher.start()
        self.addCleanup(self._patcher.stop)

    def test_broadcast_publishes_to_table_channel(self):
        import asyncio
        server = AsyncMock()
        r = asyncio.run(self.handler.handle_message(
            server, self.ws, "/", {"type": "slot_spin", "bet": 10}
        ))
        self.assertEqual(r["type"], "slot_result")
        self.assertEqual(r["spin"]["id"], 7)
        self.assertTrue(server.publish.called)
        args, _ = server.publish.call_args
        self.assertEqual(args[0], "casino:table:slots-test")


if __name__ == "__main__":
    unittest.main()
