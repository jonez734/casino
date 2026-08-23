#!/usr/bin/env python3
"""Regression tests for ``casino.lib.CasinoPlayer`` door-mode lifecycle.

Pins the lazy-but-auditable casino player contract from the door-mode
side:

- ``CasinoPlayer.__init__`` materializes the matching
  ``casino.__player`` row on first construction so the bottombar,
  stats menu, and table-seat filter see real values.
- ``self.credits`` / ``self.lastplayed`` / ``self.stats`` are populated
  from the row, not the placeholder ``1000`` / ``None`` / ``{}``.
- A debug-level audit echo fires the first time a member is
  auto-materialized via ``casino --debug``; subsequent constructions
  for the same member are silent.

Skipped if ``CASINO_TEST_DB`` is not set in the environment.
"""

from __future__ import annotations

import argparse
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, "/home/opencode/data/work/casino/src")


DB_ENV = "CASINO_TEST_DB"
DOOR_MONIKER = "door_player_test_user"


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


def _ensure_member(cur, moniker: str, *, credits: int = 250) -> None:
    """Insert a member with deterministic credits so the door-mode
    constructor's balance / lastplayed assertions are reproducible.
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


@unittest.skipUnless(_db_available(), f"{DB_ENV} env var not set; skipping DB tests")
class TestDoorCasinoPlayer(unittest.TestCase):
    """The door-mode ``CasinoPlayer`` facade must materialize the row."""

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
            _delete_test_member(cur, DOOR_MONIKER)
            _ensure_member(cur, DOOR_MONIKER, credits=250)

    def tearDown(self):
        from bbsengine6 import database
        with database.connect(self._args) as conn, database.cursor(conn) as cur:
            _delete_test_member(cur, DOOR_MONIKER)

    def test_door_casino_player_init_creates_player_row(self):
        """Constructing ``CasinoPlayer`` for a fresh member creates the
        ``casino.__player`` row immediately. Before this change, the
        row was only ever created on the WS-client auth path, leaving
        the door-mode stats menu and bottombar rendering placeholders.
        """
        from bbsengine6 import database

        from casino.lib import CasinoPlayer

        with database.connect(self._args) as conn, database.cursor(conn) as cur:
            cur.execute(
                "SELECT COUNT(*) AS n FROM casino.__player "
                "WHERE moniker = %s",
                (DOOR_MONIKER,),
            )
            self.assertEqual(cur.fetchone()["n"], 0)

        CasinoPlayer(self._args, membermoniker=DOOR_MONIKER, pool=None)

        with database.connect(self._args) as conn, database.cursor(conn) as cur:
            cur.execute(
                "SELECT membermoniker, moniker, location, lastplayed, attrs "
                "FROM casino.__player WHERE moniker = %s",
                (DOOR_MONIKER,),
            )
            row = cur.fetchone()
            self.assertIsNotNone(row, "casino.__player row must exist after init")
            self.assertEqual(row["membermoniker"], DOOR_MONIKER)
            self.assertEqual(row["moniker"], DOOR_MONIKER)
            self.assertEqual(row["location"], "casino")
            self.assertIsNone(
                row["lastplayed"],
                "freshly materialized row has lastplayed=NULL until first play",
            )
            self.assertEqual(row["attrs"], {})

    def test_door_casino_player_init_populates_credits_and_stats(self):
        """``self.credits`` / ``self.stats`` come from the row, not the
        placeholder ``1000`` / ``{}`` defaults. ``lastplayed`` is
        ``None`` for a fresh row but populated after a stats update.
        """
        from casino.lib import CasinoPlayer

        player = CasinoPlayer(self._args, membermoniker=DOOR_MONIKER, pool=None)

        # Credits come from engine.__member.credits via DAL read, so
        # they reflect the seed value (250), not the placeholder (1000).
        self.assertEqual(player.credits, 250)
        self.assertEqual(player.stats, {})
        self.assertIsNone(player.lastplayed)

    def test_door_casino_player_init_emits_audit_echo_on_first_create(self):
        """The first construction for a fresh member emits one
        debug-level audit echo. A second construction for the same
        member (the row already exists) is silent.
        """
        from bbsengine6 import io

        from casino.lib import CasinoPlayer

        with patch.object(io, "echo") as mocked_echo:
            CasinoPlayer(self._args, membermoniker=DOOR_MONIKER, pool=None)
            audit_calls = [
                c for c in mocked_echo.call_args_list
                if "auto-creating" in str(c)
            ]
            self.assertEqual(
                len(audit_calls),
                1,
                f"expected one audit echo on first create, got {len(audit_calls)}",
            )
            self.assertIn(DOOR_MONIKER, str(audit_calls[0]))
            # Audit echos are debug-level so production output stays clean.
            self.assertEqual(audit_calls[0].kwargs.get("level"), "debug")

        with patch.object(io, "echo") as mocked_echo:
            CasinoPlayer(self._args, membermoniker=DOOR_MONIKER, pool=None)
            audit_calls = [
                c for c in mocked_echo.call_args_list
                if "auto-creating" in str(c)
            ]
            self.assertEqual(
                len(audit_calls),
                0,
                "second construction must not re-emit the audit echo",
            )


if __name__ == "__main__":
    unittest.main()
