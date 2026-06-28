#!/usr/bin/env python3
# casino/tests/test_player_service.py
# Regression tests for casino.dal.player and PlayerService.
#
# Skipped if CASINO_TEST_DB is not set in the environment.

import argparse
import os
import sys
import unittest

sys.path.insert(0, "/home/opencode/data/work/casino/src")


DB_ENV = "CASINO_TEST_DB"
TEST_MONIKER = "null_credits_test_user"


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


def _ensure_null_credits_member(cur, moniker: str) -> None:
    """Insert a member with credits=NULL. Idempotent: if the member exists,
    force credits back to NULL so the test is reproducible.

    The engine.__member schema requires NOT NULL on email (but not on
    password or credits). We insert with a placeholder email and no
    password, then force credits to NULL. A NULL password makes
    `has_password()` return False, which lets the auth flow bypass the
    password check and reach the balance lookup — that's the path this
    test is exercising.
    """
    cur.execute(
        "INSERT INTO engine.__member (moniker, email) VALUES (%s, %s) "
        "ON CONFLICT (moniker) DO NOTHING",
        (moniker, f"{moniker}@test.local"),
    )
    cur.execute(
        "UPDATE engine.__member SET password = NULL, credits = NULL "
        "WHERE moniker = %s",
        (moniker,),
    )


def _delete_test_member(cur, moniker: str) -> None:
    cur.execute("DELETE FROM casino.__player WHERE membermoniker = %s", (moniker,))
    cur.execute("DELETE FROM engine.__member WHERE moniker = %s", (moniker,))


def _credits(cur, moniker: str):
    cur.execute(
        "SELECT credits FROM engine.__member WHERE moniker = %s", (moniker,)
    )
    row = cur.fetchone()
    return None if row is None else row["credits"]


@unittest.skipUnless(_db_available(), f"{DB_ENV} env var not set; skipping DB tests")
class TestPlayerService(unittest.TestCase):
    """Regression tests for the NULL-credits crash on auth."""

    @classmethod
    def setUpClass(cls):
        from bbsengine6 import database
        cls._args = _make_args()
        with database.connect(cls._args) as conn:
            with database.cursor(conn) as cur:
                cur.execute("SELECT 1")
                cur.fetchone()

    def setUp(self):
        from bbsengine6 import database
        with database.connect(self._args) as conn:
            with database.cursor(conn) as cur:
                _delete_test_member(cur, TEST_MONIKER)
                _ensure_null_credits_member(cur, TEST_MONIKER)

    def tearDown(self):
        from bbsengine6 import database
        with database.connect(self._args) as conn:
            with database.cursor(conn) as cur:
                _delete_test_member(cur, TEST_MONIKER)

    def test_get_player_balance_returns_zero_on_null_credits(self):
        """dal.player.get_player_balance must return 0, not raise, when
        engine.__member.credits IS NULL."""
        from casino.dal import player as dal_player

        # Sanity: row exists with credits NULL.
        from bbsengine6 import database
        with database.connect(self._args) as conn:
            with database.cursor(conn) as cur:
                self.assertIsNone(_credits(cur, TEST_MONIKER))

        balance = dal_player.get_player_balance(self._args, TEST_MONIKER)
        self.assertEqual(balance, 0)

    def test_get_player_balance_returns_value_on_non_null_credits(self):
        """dal.player.get_player_balance must return the int value when
        credits is not NULL."""
        from bbsengine6 import database
        from casino.dal import player as dal_player

        with database.connect(self._args) as conn:
            with database.cursor(conn) as cur:
                cur.execute(
                    "UPDATE engine.__member SET credits = 1234 WHERE moniker = %s",
                    (TEST_MONIKER,),
                )

        balance = dal_player.get_player_balance(self._args, TEST_MONIKER)
        self.assertEqual(balance, 1234)

    def test_get_player_balance_does_not_mutate_null_credits(self):
        """The DAL read must not backfill NULL credits to 0. Phase 2
        (schema migration) is what makes NULL impossible; until then, a
        read must leave the column as-is."""
        from bbsengine6 import database
        from casino.dal import player as dal_player

        dal_player.get_player_balance(self._args, TEST_MONIKER)
        with database.connect(self._args) as conn:
            with database.cursor(conn) as cur:
                self.assertIsNone(_credits(cur, TEST_MONIKER))

    def test_player_service_authenticate_succeeds_on_null_credits(self):
        """End-to-end: PlayerService.authenticate must not raise TypeError
        and must return balance=0 for a member with credits=NULL."""
        from casino.services.player import PlayerService

        service = PlayerService(self._args)
        result = service.authenticate(TEST_MONIKER, "any")
        self.assertTrue(result.get("success"))
        self.assertEqual(result.get("moniker"), TEST_MONIKER)
        self.assertEqual(result.get("balance"), 0)


if __name__ == "__main__":
    unittest.main()
