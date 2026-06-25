#!/usr/bin/env python3
# casino/tests/test_slots_integration.py
# Integration tests that require a live PostgreSQL database.
#
# Skipped if CASINO_TEST_DB is not set in the environment.

import argparse
import os
import random
import sys
import unittest

sys.path.insert(0, "/home/opencode/data/work/casino/src")


DB_ENV = "CASINO_TEST_DB"


def _db_available() -> bool:
    return bool(os.environ.get(DB_ENV))


def _make_args():
    return argparse.Namespace(
        databasename=os.environ.get(DB_ENV, "casino_test"),
        database=os.environ.get(DB_ENV, "casino_test"),
        databasehost=os.environ.get("CASINO_TEST_DBHOST", "localhost"),
        databaseport=int(os.environ.get("CASINO_TEST_DBPORT", "5432")),
        databaseuser=os.environ.get("CASINO_TEST_DBUSER", "postgres"),
        databasepassword=os.environ.get("CASINO_TEST_DBPASSWORD", ""),
        debug=False,
    )


def _ensure_member(cur, moniker: str) -> None:
    """Make sure a test member exists; idempotent."""
    cur.execute(
        "INSERT INTO engine.__member (moniker, loginid) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (moniker, moniker),
    )


def _credit(cur, moniker: str, amount: int) -> None:
    cur.execute(
        "INSERT INTO bank.__account (moniker, balance) VALUES (%s, %s) "
        "ON CONFLICT (moniker) DO UPDATE SET balance = bank.__account.balance + EXCLUDED.balance",
        (moniker, amount),
    )


def _balance(cur, moniker: str) -> int:
    cur.execute("SELECT balance FROM bank.__account WHERE moniker = %s", (moniker,))
    row = cur.fetchone()
    return int(row["balance"]) if row else 0


def _delete_table(cur, moniker: str) -> None:
    cur.execute("DELETE FROM casino.__slot_spin WHERE table_moniker = %s", (moniker,))
    cur.execute("DELETE FROM casino.__bank_table WHERE table_moniker = %s", (moniker,))
    cur.execute("DELETE FROM casino.__table WHERE moniker = %s", (moniker,))


@unittest.skipUnless(_db_available(), f"{DB_ENV} env var not set; skipping DB integration tests")
class TestSlotIntegration(unittest.TestCase):
    """End-to-end spin flow against a real PostgreSQL database."""

    @classmethod
    def setUpClass(cls):
        from bbsengine6 import database
        cls._args = _make_args()
        # Validate the DB connection is reachable
        with database.connect(cls._args) as conn:
            with database.cursor(conn) as cur:
                cur.execute("SELECT 1")
                cur.fetchone()

    def setUp(self):
        from bbsengine6 import database
        from casino.services.slots import invalidate_dealer
        invalidate_dealer("integ-slots")
        with database.connect(self._args) as conn:
            with database.cursor(conn) as cur:
                _delete_table(cur, "integ-slots")
                _ensure_member(cur, "alice")
                _ensure_member(cur, "bob")
                _credit(cur, "alice", 10000)
                _credit(cur, "bob", 100)
        self._baseline_alice = 10000
        self._baseline_bob = 100

    def tearDown(self):
        from bbsengine6 import database
        with database.connect(self._args) as conn:
            with database.cursor(conn) as cur:
                _delete_table(cur, "integ-slots")
                _credit(cur, "alice", 0)
                _credit(cur, "bob", 0)

    def _create_slots_table(self, min_bet=1, max_bet=1000):
        from casino.dal import table as dal_table
        dal_table.create_table(self._args, "slots", "alice",
                               min_bet=min_bet, max_bet=max_bet,
                               moniker="integ-slots")

    def test_full_spin_debits_credits_and_records(self):
        from casino.services.slots import handle_spin
        from bbsengine6 import database
        from casino.dal import slots as dal_slots

        self._create_slots_table(min_bet=1, max_bet=1000)
        before = self._baseline_alice
        r = handle_spin(self._args, "integ-slots", "alice", 10)
        self.assertTrue(r["success"])
        # Balance changed by net (payout - 10)
        with database.connect(self._args) as conn:
            with database.cursor(conn) as cur:
                after = _balance(cur, "alice")
        self.assertEqual(after, before + r["spin"]["net"])
        # Spin row exists
        history = dal_slots.get_spin_history(self._args, "alice", limit=5)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["table_moniker"], "integ-slots")
        self.assertEqual(int(history[0]["bet"]), 10)

    def test_insufficient_funds_rolls_back(self):
        from casino.services.slots import handle_spin
        from bbsengine6 import database
        from casino.dal import slots as dal_slots

        self._create_slots_table(min_bet=1, max_bet=1000)
        # bob has only 100, bet 500
        r = handle_spin(self._args, "integ-slots", "bob", 500)
        self.assertFalse(r["success"])
        self.assertEqual(r["code"], "insufficient_funds")
        # bob's balance is unchanged
        with database.connect(self._args) as conn:
            with database.cursor(conn) as cur:
                self.assertEqual(_balance(cur, "bob"), self._baseline_bob)
        # No spin row was written
        history = dal_slots.get_spin_history(self._args, "bob", limit=5)
        self.assertEqual(history, [])

    def test_bet_below_min_rejected(self):
        from casino.services.slots import handle_spin

        self._create_slots_table(min_bet=10, max_bet=1000)
        r = handle_spin(self._args, "integ-slots", "alice", 1)
        self.assertFalse(r["success"])
        self.assertEqual(r["code"], "bet_below_min")

    def test_bet_above_max_rejected(self):
        from casino.services.slots import handle_spin

        self._create_slots_table(min_bet=1, max_bet=100)
        r = handle_spin(self._args, "integ-slots", "alice", 500)
        self.assertFalse(r["success"])
        self.assertEqual(r["code"], "bet_above_max")

    def test_stats_track_spins_and_biggest_win(self):
        from casino.services.slots import handle_spin
        from casino.dal import player as dal_player

        self._create_slots_table(min_bet=1, max_bet=1000)
        # Run several spins
        for _ in range(5):
            r = handle_spin(self._args, "integ-slots", "alice", 5)
            self.assertTrue(r["success"])
        stats = dal_player.get_player_stats(self._args, "alice")
        self.assertEqual(stats.get("slots.spins"), 5)
        self.assertGreaterEqual(stats.get("slots.wins", 0), 0)
        self.assertIn("slots.net", stats)
        if stats.get("slots.wins", 0) > 0:
            self.assertIn("slots.biggest_win", stats)
            self.assertGreater(stats["slots.biggest_win"], 0)

    def test_history_newest_first(self):
        from casino.services.slots import handle_spin
        from casino.dal import slots as dal_slots

        self._create_slots_table(min_bet=1, max_bet=1000)
        for i in range(3):
            r = handle_spin(self._args, "integ-slots", "alice", 5)
            self.assertTrue(r["success"], msg=f"spin {i} failed: {r}")
        history = dal_slots.get_spin_history(self._args, "alice", limit=10)
        self.assertEqual(len(history), 3)
        # Newest first: spun_at descending
        for i in range(len(history) - 1):
            self.assertGreaterEqual(history[i]["spun_at"], history[i + 1]["spun_at"])


class TestSlotRTPEmpirical(unittest.TestCase):
    """Long-run empirical RTP sanity check. Runs against the lib directly,
    no DB required.
    """

    def test_10k_spin_rtp_in_window(self):
        from casino.slots import lib
        from casino.slots.dealer import SlotDealer

        rng = lib.RNG(random.Random(42))
        dealer = SlotDealer(
            lib.default_reels(lib.DEFAULT_SYMBOLS, rng),
            lib.Paytable(), rng,
        )
        n = 10_000
        total_payout = 0
        wins = 0
        for _ in range(n):
            r = dealer.play(bet=1)
            total_payout += r.payout
            if r.did_win:
                wins += 1
        rtp = total_payout / n
        # Should be within +/- 0.07 of the 0.92 target with 10k samples
        self.assertGreater(rtp, 0.85)
        self.assertLess(rtp, 0.99)
        # Win rate should be at least 30% (lots of small wins)
        self.assertGreater(wins / n, 0.25)


if __name__ == "__main__":
    unittest.main()
