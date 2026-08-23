#!/usr/bin/env python3
# casino/tests/test_player_service.py
# Regression tests for casino.dal.player and PlayerService.
#
# Skipped if CASINO_TEST_DB is not set in the environment.

import argparse
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, "/home/opencode/data/work/casino/src")


DB_ENV = "CASINO_TEST_DB"
TEST_MONIKER = "null_credits_test_user"
ENSURE_MONIKER = "ensure_player_test_user"


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


def _ensure_simple_member(cur, moniker: str, *, credits: int = 100) -> None:
    """Insert a member with a known non-null credits value.

    Used by ``TestEnsureCasinoPlayer`` so the balance / stats assertions
    are deterministic against a freshly-materialized casino.__player
    row. ``ON CONFLICT`` so reruns against a dirty DB self-heal.
    """
    cur.execute(
        "INSERT INTO engine.__member (moniker, email, credits) "
        "VALUES (%s, %s, %s) "
        "ON CONFLICT (moniker) DO UPDATE SET credits = EXCLUDED.credits",
        (moniker, f"{moniker}@test.local", credits),
    )


def _delete_test_member(cur, moniker: str) -> None:
    cur.execute("DELETE FROM casino.__player WHERE moniker = %s", (moniker,))
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
        with database.connect(cls._args) as conn, database.cursor(conn) as cur:
            cur.execute("SELECT 1")
            cur.fetchone()

    def setUp(self):
        from bbsengine6 import database
        with database.connect(self._args) as conn, database.cursor(conn) as cur:
            _delete_test_member(cur, TEST_MONIKER)
            _ensure_null_credits_member(cur, TEST_MONIKER)

    def tearDown(self):
        from bbsengine6 import database
        with database.connect(self._args) as conn, database.cursor(conn) as cur:
            _delete_test_member(cur, TEST_MONIKER)

    def test_get_player_balance_returns_zero_on_null_credits(self):
        """dal.player.get_player_balance must return 0, not raise, when
        engine.__member.credits IS NULL."""
        # Sanity: row exists with credits NULL.
        from bbsengine6 import database

        from casino.dal import player as dal_player
        with database.connect(self._args) as conn, database.cursor(conn) as cur:
            self.assertIsNone(_credits(cur, TEST_MONIKER))

        balance = dal_player.get_player_balance(self._args, TEST_MONIKER)
        self.assertEqual(balance, 0)

    def test_get_player_balance_returns_value_on_non_null_credits(self):
        """dal.player.get_player_balance must return the int value when
        credits is not NULL."""
        from bbsengine6 import database

        from casino.dal import player as dal_player

        with database.connect(self._args) as conn, database.cursor(conn) as cur:
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
        with database.connect(self._args) as conn, database.cursor(conn) as cur:
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


@unittest.skipUnless(_db_available(), f"{DB_ENV} env var not set; skipping DB tests")
class TestEnsureCasinoPlayer(unittest.TestCase):
    """Regression tests for :func:`casino.services.player.ensure_casino_player`.

    Pins the lazy-but-auditable lifecycle: idempotent materialization,
    audit-echo on create, audit-echo suppressed when disabled, and the
    refactor that ``PlayerService.authenticate`` calls the helper
    instead of poking ``dal.player`` directly.
    """

    @classmethod
    def setUpClass(cls):
        from bbsengine6 import database
        cls._args = _make_args()
        with database.connect(cls._args) as conn, database.cursor(conn) as cur:
            cur.execute("SELECT 1")
            cur.fetchone()

    def setUp(self):
        from bbsengine6 import database
        with database.connect(self._args) as conn, database.cursor(conn) as cur:
            _delete_test_member(cur, ENSURE_MONIKER)
            _ensure_simple_member(cur, ENSURE_MONIKER, credits=500)

    def tearDown(self):
        from bbsengine6 import database
        with database.connect(self._args) as conn, database.cursor(conn) as cur:
            _delete_test_member(cur, ENSURE_MONIKER)

    def test_ensure_casino_player_is_idempotent(self):
        """Calling ``ensure_casino_player`` twice for the same member
        returns the same row and does not create a duplicate. The
        second call is a pure read.
        """
        from bbsengine6 import database

        from casino.services.player import ensure_casino_player

        first = ensure_casino_player(self._args, ENSURE_MONIKER, audit=False)
        self.assertEqual(first["membermoniker"], ENSURE_MONIKER)
        self.assertEqual(first["moniker"], ENSURE_MONIKER)

        with database.connect(self._args) as conn, database.cursor(conn) as cur:
            cur.execute(
                "SELECT COUNT(*) AS n FROM casino.__player "
                "WHERE moniker = %s",
                (ENSURE_MONIKER,),
            )
            row = cur.fetchone()
            self.assertEqual(row["n"], 1)

        second = ensure_casino_player(self._args, ENSURE_MONIKER, audit=False)
        self.assertEqual(second["membermoniker"], ENSURE_MONIKER)
        self.assertEqual(first.get("location"), second.get("location"))

    def test_ensure_casino_player_emits_audit_on_create(self):
        """When ``audit=True`` and the row is newly created, one
        debug-level echo is emitted containing the membermoniker. The
        second call does NOT emit because the row already exists.
        """
        from bbsengine6 import io

        from casino.services.player import ensure_casino_player

        with patch.object(io, "echo") as mocked_echo:
            ensure_casino_player(self._args, ENSURE_MONIKER, audit=True)
            create_calls = [
                c for c in mocked_echo.call_args_list
                if "auto-creating" in str(c)
            ]
            self.assertEqual(
                len(create_calls),
                1,
                f"expected exactly one audit echo on create, got {len(create_calls)}",
            )
            self.assertIn(ENSURE_MONIKER, str(create_calls[0]))

        with patch.object(io, "echo") as mocked_echo:
            ensure_casino_player(self._args, ENSURE_MONIKER, audit=True)
            create_calls = [
                c for c in mocked_echo.call_args_list
                if "auto-creating" in str(c)
            ]
            self.assertEqual(
                len(create_calls),
                0,
                "audit echo must not fire when the row already exists",
            )

    def test_ensure_casino_player_does_not_audit_when_disabled(self):
        """``audit=False`` (the WS-client default) suppresses the
        audit echo entirely, even on the create path.
        """
        from bbsengine6 import io

        from casino.services.player import ensure_casino_player

        with patch.object(io, "echo") as mocked_echo:
            ensure_casino_player(self._args, ENSURE_MONIKER, audit=False)
            audit_calls = [
                c for c in mocked_echo.call_args_list
                if "auto-creating" in str(c)
            ]
            self.assertEqual(
                len(audit_calls),
                0,
                "audit=False must suppress the debug echo on create",
            )

    def test_player_service_authenticate_calls_ensure_casino_player(self):
        """``PlayerService.authenticate`` goes through
        ``ensure_casino_player`` (not ``dal.player.get_or_create_player``
        directly) so both entry paths converge on the same lifecycle.
        """
        from casino.services.player import PlayerService

        service = PlayerService(self._args)
        with patch(
            "casino.services.player.ensure_casino_player"
        ) as mock_ensure, patch(
            "casino.services.player.dal_player.get_player_balance",
            return_value=0,
        ):
            mock_ensure.return_value = {
                "membermoniker": ENSURE_MONIKER,
                "location": "casino",
                "lastplayed": None,
                "attrs": {},
            }
            result = service.authenticate(ENSURE_MONIKER, "any")

        self.assertTrue(result["success"])
        mock_ensure.assert_called_once()
        # Caller passes audit=False on the WS-client path so the
        # wire output stays clean even on the first successful login.
        _, kwargs = mock_ensure.call_args
        self.assertEqual(kwargs.get("audit"), False)


if __name__ == "__main__":
    unittest.main()
