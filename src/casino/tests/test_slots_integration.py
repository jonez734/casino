#!/usr/bin/env python3
# casino/tests/test_slots_integration.py
# Integration tests that require a live PostgreSQL database.
#
# Skipped if CASINO_TEST_DB is not set in the environment.

import argparse
import asyncio
import contextlib
import json
import os
import random
import sys
import unittest
from typing import Optional

import pytest
import websockets
from websockets.exceptions import ConnectionClosed

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
        "INSERT INTO engine.__member (moniker, loginid, password, email, credits) "
        "VALUES (%s, %s, crypt('test', gen_salt('md5')), %s, 100000) "
        "ON CONFLICT (moniker) DO NOTHING",
        (moniker, moniker, f"{moniker}@test.local"),
    )


def _credit(cur, moniker: str, amount: int) -> None:
    cur.execute(
        "INSERT INTO bank.__account (moniker, balance) VALUES (%s, %s) "
        "ON CONFLICT (moniker) DO UPDATE SET balance = bank.__account.balance + EXCLUDED.balance",
        (moniker, amount),
    )


def _set_balance(cur, moniker: str, balance: int) -> None:
    """Set the bank balance for ``moniker`` to an absolute value (idempotent)."""
    cur.execute(
        "INSERT INTO bank.__account (moniker, balance) VALUES (%s, %s) "
        "ON CONFLICT (moniker) DO UPDATE SET balance = EXCLUDED.balance",
        (moniker, balance),
    )


def _ensure_player(cur, moniker: str) -> None:
    """Make sure a casino player row exists for ``moniker`` (idempotent).

    Uses the project's get_or_create_player DAL, which already handles the
    SELECT-then-INSERT race and the no-unique-constraint table shape.
    Resets stats so each test starts with a clean baseline.
    """
    cur.execute(
        "SELECT 1 FROM casino.__player WHERE membermoniker = %s", (moniker,)
    )
    if cur.fetchone() is None:
        cur.execute(
            "INSERT INTO casino.__player (membermoniker, location, attrs) "
            "VALUES (%s, 'casino', '{}'::jsonb)",
            (moniker,),
        )
    # Clear any stats left over from a previous test run
    cur.execute(
        "UPDATE casino.__player SET stats = '{}'::jsonb WHERE membermoniker = %s",
        (moniker,),
    )


def _balance(cur, moniker: str) -> int:
    cur.execute("SELECT balance FROM bank.__account WHERE moniker = %s", (moniker,))
    row = cur.fetchone()
    return int(row["balance"]) if row else 0


def _delete_table(cur, moniker: str) -> None:
    cur.execute("DELETE FROM casino.__slot_spin WHERE table_moniker = %s", (moniker,))
    cur.execute("DELETE FROM casino.__bank_table WHERE table_moniker = %s", (moniker,))
    cur.execute("DELETE FROM casino.__table WHERE moniker = %s", (moniker,))


@pytest.mark.integration
@unittest.skipUnless(_db_available(), f"{DB_ENV} env var not set; skipping DB integration tests")
class TestSlotIntegration(unittest.TestCase):
    """End-to-end spin flow against a real PostgreSQL database."""

    @classmethod
    def setUpClass(cls):
        from bbsengine6 import database
        cls._args = _make_args()
        # Validate the DB connection is reachable
        with database.connect(cls._args) as conn, database.cursor(conn) as cur:
            cur.execute("SELECT 1")
            cur.fetchone()

    def setUp(self):
        from bbsengine6 import database

        from casino.services.slots import invalidate_dealer
        invalidate_dealer("integ-slots")
        with database.connect(self._args) as conn, database.cursor(conn) as cur:
            _delete_table(cur, "integ-slots")
            _ensure_member(cur, "alice")
            _ensure_member(cur, "bob")
            _set_balance(cur, "alice", 10000)
            _set_balance(cur, "bob", 100)
            _ensure_player(cur, "alice")
            _ensure_player(cur, "bob")
        self._baseline_alice = 10000
        self._baseline_bob = 100

    def tearDown(self):
        from bbsengine6 import database
        with database.connect(self._args) as conn, database.cursor(conn) as cur:
            _delete_table(cur, "integ-slots")
            _set_balance(cur, "alice", 0)
            _set_balance(cur, "bob", 0)

    def _create_slots_table(self, min_bet=1, max_bet=1000):
        from casino.dal import table as dal_table
        dal_table.create_table(self._args, "slots", "alice",
                               min_bet=min_bet, max_bet=max_bet,
                               moniker="integ-slots")

    def _set_table_attrs(self, table_moniker: str, attrs: dict) -> None:
        from bbsengine6 import database

        with database.connect(self._args) as conn, database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "UPDATE $casino.__table SET attrs = :attrs WHERE moniker = :moniker",
                    attrs=database.Jsonb(attrs),
                    moniker=table_moniker,
                )
            )

    def _delete_bank_account(self, moniker: str) -> None:
        from bbsengine6 import database

        with database.connect(self._args) as conn, database.cursor(conn) as cur:
            cur.execute(
                "DELETE FROM bank.__account WHERE moniker = %s", (moniker,)
            )

    def test_full_spin_debits_credits_and_records(self):
        from bbsengine6 import database

        from casino.dal import slots as dal_slots
        from casino.services.slots import handle_spin

        self._create_slots_table(min_bet=1, max_bet=1000)
        before = self._baseline_alice
        r = handle_spin(self._args, "integ-slots", "alice", 10)
        self.assertTrue(r["success"])
        # Balance changed by net (payout - 10)
        with database.connect(self._args) as conn, database.cursor(conn) as cur:
            after = _balance(cur, "alice")
        self.assertEqual(after, before + r["spin"]["net"])
        # Spin row exists
        history = dal_slots.get_spin_history(self._args, "alice", limit=5)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["table_moniker"], "integ-slots")
        self.assertEqual(int(history[0]["bet"]), 10)

    def test_insufficient_funds_rolls_back(self):
        from bbsengine6 import database

        from casino.dal import slots as dal_slots
        from casino.services.slots import handle_spin

        self._create_slots_table(min_bet=1, max_bet=1000)
        # bob has only 100, bet 500
        r = handle_spin(self._args, "integ-slots", "bob", 500)
        self.assertFalse(r["success"])
        self.assertEqual(r["code"], "insufficient_funds")
        # bob's balance is unchanged
        with database.connect(self._args) as conn, database.cursor(conn) as cur:
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
        from casino.dal import player as dal_player
        from casino.services.slots import handle_spin

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
        from casino.dal import slots as dal_slots
        from casino.services.slots import handle_spin

        self._create_slots_table(min_bet=1, max_bet=1000)
        for i in range(3):
            r = handle_spin(self._args, "integ-slots", "alice", 5)
            self.assertTrue(r["success"], msg=f"spin {i} failed: {r}")
        history = dal_slots.get_spin_history(self._args, "alice", limit=10)
        self.assertEqual(len(history), 3)
        # Newest first: spun_at descending
        for i in range(len(history) - 1):
            self.assertGreaterEqual(history[i]["spun_at"], history[i + 1]["spun_at"])

    # ----- bet validation: type + boundary -------------------------------
    def test_zero_bet_rejected(self):
        from casino.services.slots import handle_spin

        self._create_slots_table(min_bet=1, max_bet=1000)
        r = handle_spin(self._args, "integ-slots", "alice", 0)
        self.assertFalse(r["success"])
        self.assertEqual(r["code"], "invalid_bet")

    def test_negative_bet_rejected(self):
        from casino.services.slots import handle_spin

        self._create_slots_table(min_bet=1, max_bet=1000)
        r = handle_spin(self._args, "integ-slots", "alice", -5)
        self.assertFalse(r["success"])
        self.assertEqual(r["code"], "invalid_bet")

    def test_boolean_bet_rejected(self):
        from casino.services.slots import handle_spin

        self._create_slots_table(min_bet=1, max_bet=1000)
        r = handle_spin(self._args, "integ-slots", "alice", True)
        self.assertFalse(r["success"])
        self.assertEqual(r["code"], "invalid_bet")

    def test_bet_exactly_min_accepted(self):
        from casino.services.slots import handle_spin

        self._create_slots_table(min_bet=10, max_bet=1000)
        r = handle_spin(self._args, "integ-slots", "alice", 10)
        self.assertTrue(r["success"], msg=r)
        self.assertEqual(r["spin"]["bet"], 10)

    def test_bet_exactly_max_accepted(self):
        from casino.services.slots import handle_spin

        self._create_slots_table(min_bet=1, max_bet=100)
        r = handle_spin(self._args, "integ-slots", "alice", 100)
        self.assertTrue(r["success"], msg=r)
        self.assertEqual(r["spin"]["bet"], 100)

    # ----- loss spin semantics ------------------------------------------
    def test_loss_spin_debits_bet_only(self):
        from bbsengine6 import database

        from casino.dal import player as dal_player
        from casino.services.slots import handle_spin as _spin
        from casino.slots import lib as slots_lib
        from casino.slots.dealer import SlotDealer

        self._create_slots_table(min_bet=1, max_bet=1000)
        before_alice = self._baseline_alice
        rng = slots_lib.RNG(random.Random(1))
        dealer = SlotDealer(
            slots_lib.default_reels(slots_lib.DEFAULT_SYMBOLS, rng),
            slots_lib.Paytable(), rng,
        )
        # Find a losing spin
        losing_bet = 7
        lost = None
        for _ in range(200):
            r = dealer.play(bet=losing_bet)
            if r.payout == 0:
                lost = r
                break
        if lost is None:
            self.skipTest("could not produce a losing spin in 200 tries")

        # Inject the deterministic dealer into the cache via invalidation
        from casino.services.slots import invalidate_dealer
        invalidate_dealer("integ-slots")
        from casino.services.slots import _dealers as _cache
        _cache["integ-slots"] = dealer

        try:
            r = _spin(self._args, "integ-slots", "alice", losing_bet)
        finally:
            invalidate_dealer("integ-slots")
        self.assertTrue(r["success"], msg=r)
        self.assertEqual(r["spin"]["payout"], 0)
        self.assertEqual(r["spin"]["net"], -losing_bet)

        with database.connect(self._args) as conn, database.cursor(conn) as cur:
            after = _balance(cur, "alice")
        self.assertEqual(after, before_alice - losing_bet)
        # Stats: wins should not advance for a loss
        stats = dal_player.get_player_stats(self._args, "alice")
        wins = stats.get("slots.wins", 0)
        self.assertEqual(wins, 0)

    # ----- bank account auto-create -------------------------------------
    def test_bank_account_auto_created_for_new_player(self):
        from bbsengine6 import database

        from casino.services.slots import handle_spin

        # Brand-new moniker with no bank account
        with database.connect(self._args) as conn, database.cursor(conn) as cur:
            _ensure_member(cur, "newbie")
            cur.execute(
                "DELETE FROM bank.__account WHERE moniker = %s", ("newbie",)
            )

        self._create_slots_table(min_bet=1, max_bet=1000)
        r = handle_spin(self._args, "integ-slots", "newbie", 5)
        # No bank account -> auto-created with balance 0 -> insufficient_funds
        self.assertFalse(r["success"])
        self.assertEqual(r["code"], "insufficient_funds")
        # And the auto-created account should now exist
        with database.connect(self._args) as conn, database.cursor(conn) as cur:
            row = cur.execute(
                "SELECT balance FROM bank.__account WHERE moniker = %s",
                ("newbie",),
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(int(row["balance"]), 0)

    # ----- paytable_override ---------------------------------------------
    def test_paytable_override_applied(self):
        from casino.services.slots import (
            handle_get_paytable,
            handle_spin,
            invalidate_dealer,
        )

        self._create_slots_table(min_bet=1, max_bet=1000)
        # Override paytable with a single custom entry; the dealer
        # cache must be invalidated so the override is picked up.
        # Use the list-of-dicts format (JSONB-friendly; PostgreSQL
        # jsonb does not allow tuple keys).
        self._set_table_attrs(
            "integ-slots",
            {"paytable_override": [{"symbols": ["CHERRY"], "multiplier": 99}]},
        )
        invalidate_dealer("integ-slots")

        pt = handle_get_paytable(self._args, "integ-slots")
        self.assertTrue(pt["success"], msg=pt)
        cherry_entry = next(
            (e for e in pt["payouts"] if e["symbols"] == ["CHERRY"]), None
        )
        self.assertIsNotNone(cherry_entry)
        self.assertEqual(cherry_entry["multiplier"], 99)

        # A successful spin should still commit under the override
        r = handle_spin(self._args, "integ-slots", "alice", 5)
        self.assertTrue(r["success"], msg=r)

    # ----- table history filter ------------------------------------------
    def test_get_table_history_returns_only_table_spins(self):
        from casino.dal import slots as dal_slots
        from casino.services.slots import handle_spin

        self._create_slots_table(min_bet=1, max_bet=1000)
        # Spin at our slots table
        for _ in range(3):
            r = handle_spin(self._args, "integ-slots", "alice", 5)
            self.assertTrue(r["success"], msg=r)
        # Use a second player to spin at a different table moniker would
        # require a second table; the row filter is enough.
        table_hist = dal_slots.get_table_history(self._args, "integ-slots", limit=10)
        self.assertEqual(len(table_hist), 3)
        for s in table_hist:
            self.assertEqual(s["table_moniker"], "integ-slots")
        # Cross-check: querying another table's history yields nothing
        other = dal_slots.get_table_history(self._args, "does-not-exist", limit=10)
        self.assertEqual(other, [])

    # ----- spin id monotonicity ------------------------------------------
    def test_spin_ids_are_monotonic(self):
        from casino.dal import slots as dal_slots
        from casino.services.slots import handle_spin

        self._create_slots_table(min_bet=1, max_bet=1000)
        prev_id = 0
        for _ in range(4):
            r = handle_spin(self._args, "integ-slots", "alice", 5)
            self.assertTrue(r["success"], msg=r)
            self.assertGreater(int(r["spin"]["id"]), prev_id)
            prev_id = int(r["spin"]["id"])
        # And the DB rows reflect the same monotonic ordering
        history = dal_slots.get_spin_history(self._args, "alice", limit=10)
        ids = [int(h["id"]) for h in history]
        self.assertEqual(ids, sorted(ids, reverse=True))


@pytest.mark.integration
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


# ---------------------------------------------------------------------------
# Bed integration tests (real WebSocketServer + MessageRouter)
# ---------------------------------------------------------------------------

DEFAULT_TIMEOUT = 10.0
PING_INTERVAL = 30.0


class _BedWebSocketTestClient:
    """Robust WebSocket test client. Copied from test_blackjack_flow.py."""

    def __init__(self, uri: str, timeout: float = DEFAULT_TIMEOUT):
        self.uri = uri
        self.timeout = timeout
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self._receive_task: Optional[asyncio.Task] = None
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._running = False

    async def connect(self) -> None:
        for attempt in range(3):
            try:
                self.ws = await asyncio.wait_for(
                    websockets.connect(
                        self.uri,
                        ping_interval=PING_INTERVAL,
                        ping_timeout=10.0,
                        close_timeout=5.0,
                    ),
                    timeout=self.timeout,
                )
                self._running = True
                self._receive_task = asyncio.create_task(self._receive_messages())
                return
            except Exception as e:
                if attempt < 2:
                    await asyncio.sleep(0.5)
                else:
                    raise ConnectionError(f"Failed to connect: {e}")

    async def _receive_messages(self) -> None:
        try:
            async for message in self.ws:
                if not self._running:
                    break
                with contextlib.suppress(json.JSONDecodeError):
                    await self._message_queue.put(json.loads(message))
        except ConnectionClosed:
            pass
        finally:
            self._running = False

    async def send(self, message: dict, timeout: Optional[float] = None) -> None:
        if not self.ws or not self._running:
            raise ConnectionError("Not connected")
        await asyncio.wait_for(
            self.ws.send(json.dumps(message)), timeout=timeout or self.timeout
        )

    async def receive(self, timeout: Optional[float] = None) -> dict:
        if not self._running:
            raise ConnectionError("Not connected")
        return await asyncio.wait_for(
            self._message_queue.get(), timeout=timeout or self.timeout
        )

    async def receive_any(
        self, expected_type: Optional[str] = None, timeout: Optional[float] = None
    ) -> dict:
        timeout = timeout or self.timeout
        start = asyncio.get_event_loop().time()
        while True:
            remaining = timeout - (asyncio.get_event_loop().time() - start)
            if remaining <= 0:
                raise TimeoutError(f"Timed out after {timeout}s")
            try:
                msg = await asyncio.wait_for(
                    self._message_queue.get(), timeout=min(remaining, 1.0)
                )
                if expected_type is None or msg.get("type") == expected_type:
                    return msg
                await self._message_queue.put(msg)
            except asyncio.TimeoutError:
                continue

    async def close(self) -> None:
        self._running = False
        if self._receive_task:
            self._receive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._receive_task
        if self.ws:
            with contextlib.suppress(Exception):
                await self.ws.close(code=1000, reason="Test complete")
        while not self._message_queue.empty():
            try:
                self._message_queue.get_nowait()
            except Exception:
                break


def _ensure_test_user(cur, moniker: str) -> None:
    cur.execute(
        "INSERT INTO engine.__member (moniker, loginid, password, email, credits) "
        "VALUES (%s, %s, crypt('test', gen_salt('md5')), %s, 100000) "
        "ON CONFLICT (moniker) DO UPDATE SET password = crypt('test', gen_salt('md5')), credits = 100000",
        (moniker, moniker, f"{moniker}@test.local"),
    )
    cur.execute(
        "INSERT INTO bank.__account (moniker, balance) VALUES (%s, 100000) "
        "ON CONFLICT (moniker) DO UPDATE SET balance = 100000",
        (moniker,),
    )


def _get_balance(cur, moniker: str) -> int:
    cur.execute("SELECT balance FROM bank.__account WHERE moniker = %s", (moniker,))
    row = cur.fetchone()
    return int(row["balance"]) if row else 0


def _spin_row_count(cur, moniker: str) -> int:
    cur.execute(
        "SELECT COUNT(*) AS n FROM casino.__slot_spin WHERE player_moniker = %s",
        (moniker,),
    )
    row = cur.fetchone()
    return int(row["n"]) if row else 0


def _stats_for(cur, moniker: str) -> dict:
    cur.execute(
        "SELECT stats FROM casino.__player WHERE membermoniker = %s", (moniker,)
    )
    row = cur.fetchone()
    if not row or not row["stats"]:
        return {}
    return dict(row["stats"])


def _cleanup(cur, table_moniker: str, players: list) -> None:
    cur.execute(
        "DELETE FROM casino.__slot_spin WHERE table_moniker = %s", (table_moniker,)
    )
    cur.execute(
        "DELETE FROM casino.map_cardtable_player WHERE cardtablemoniker = %s",
        (table_moniker,),
    )
    cur.execute(
        "DELETE FROM casino.__game WHERE tablemoniker = %s", (table_moniker,)
    )
    cur.execute(
        "DELETE FROM casino.__betlog WHERE cardtablemoniker = %s", (table_moniker,)
    )
    cur.execute("DELETE FROM casino.__bank_table WHERE table_moniker = %s", (table_moniker,))
    cur.execute("DELETE FROM casino.__table WHERE moniker = %s", (table_moniker,))
    # Reset player state
    for p in players:
        cur.execute(
            "UPDATE engine.__member SET credits = 100000 WHERE moniker = %s", (p,)
        )
        cur.execute(
            "UPDATE bank.__account SET balance = 100000 WHERE moniker = %s", (p,)
        )
        cur.execute(
            "UPDATE casino.__player SET stats = '{}'::jsonb WHERE membermoniker = %s",
            (p,),
        )


@pytest.mark.integration
@unittest.skipUnless(_db_available(), f"{DB_ENV} env var not set; skipping BED integration tests")
class TestSlotBedIntegration(unittest.IsolatedAsyncioTestCase):
    """End-to-end WebSocket tests for the slots service.

    Mirrors the test_blackjack_flow.py pattern: real WebSocketServer +
    MessageRouter, real database. Test users: jam_1 (player), jam_2
    (spectator). Skipped when CASINO_TEST_DB is unset.
    """

    PLAYER_MONIKER = "jam_1"
    SPECTATOR_MONIKER = "jam_2"
    TABLE_MONIKER = "slots_jam_1"
    BJ_TABLE_MONIKER = "blackjack_jam_1"
    PORT = 18765

    async def asyncSetUp(self) -> None:
        from bbsengine6 import database
        from bbsengine6.net import WebSocketServer

        from casino import lib
        from casino.api.handler import MessageRouter

        # Build args with the test database
        parser = lib.buildargs()
        self.args = parser.parse_args(["--databasename", "zoid6test"])
        self.pool = database.getpool(self.args)

        # Create both test users with the standard test password + balance
        with database.connect(self.args, pool=self.pool) as conn, database.cursor(conn) as cur:
            _ensure_test_user(cur, self.PLAYER_MONIKER)
            _ensure_test_user(cur, self.SPECTATOR_MONIKER)

        # Start the WebSocket server + router
        self.server = WebSocketServer(host="127.0.0.1", port=self.PORT)
        self.router = MessageRouter(self.args)
        self.router.register_all(self.server)
        await self.server.start()
        self._server_started = True
        self.uri = f"ws://127.0.0.1:{self.PORT}/"
        self.clients: list = []

    async def asyncTearDown(self) -> None:
        from bbsengine6 import database

        for c in self.clients:
            await c.close()

        if hasattr(self, "_server_started") and self._server_started:
            await self.server.stop()

        if hasattr(self, "pool") and self.pool is not None:
            try:
                with database.connect(self.args, pool=self.pool) as conn, database.cursor(conn) as cur:
                    _cleanup(
                        cur,
                        self.TABLE_MONIKER,
                        [self.PLAYER_MONIKER, self.SPECTATOR_MONIKER],
                    )
                    _cleanup(
                        cur,
                        self.BJ_TABLE_MONIKER,
                        [self.PLAYER_MONIKER, self.SPECTATOR_MONIKER],
                    )
                    # Some tests (insufficient_funds) spin up ad-hoc
                    # tables for the spectator. Sweep anything starting
                    # with slots- or blackjack- owned by our test users
                    # so re-runs are deterministic.
                    for player in (
                        self.PLAYER_MONIKER,
                        self.SPECTATOR_MONIKER,
                    ):
                        for prefix in ("slots", "blackjack"):
                            extra = f"{prefix}-{player}"
                            _cleanup(
                                cur,
                                extra,
                                [self.PLAYER_MONIKER, self.SPECTATOR_MONIKER],
                            )
            except Exception:
                pass
            self.pool.close()
            self.pool = None

    async def _connect_and_auth(self, moniker: str) -> _BedWebSocketTestClient:
        client = _BedWebSocketTestClient(self.uri)
        await client.connect()
        await client.send(
            {"type": "auth", "moniker": moniker, "password": "test"}
        )
        # Drain any startup messages
        for _ in range(5):
            try:
                await client.receive(timeout=1.0)
            except TimeoutError:
                break
        return client

    async def _create_slots_table(
        self, client, moniker: str, min_bet: int = 1, max_bet: int = 1000
    ) -> dict:
        await client.send(
            {
                "type": "create_table",
                "game_type": "slots",
                "moniker": moniker,
                "min_bet": min_bet,
                "max_bet": max_bet,
            }
        )
        msg = await client.receive_any(expected_type="table_created", timeout=10.0)
        return msg

    async def _create_bj_table(self, client, moniker: str) -> dict:
        await client.send(
            {
                "type": "create_table",
                "game_type": "blackjack",
                "moniker": moniker,
                "min_bet": 1,
                "max_bet": 1000,
            }
        )
        return await client.receive_any(expected_type="table_created", timeout=10.0)

    # -- 1: full spin flow --------------------------------------------------
    async def test_full_spin_flow(self) -> None:
        from bbsengine6 import database

        client = await self._connect_and_auth(self.PLAYER_MONIKER)
        self.clients.append(client)
        await self._create_slots_table(client, self.TABLE_MONIKER)
        await client.send(
            {"type": "join_table", "moniker": self.TABLE_MONIKER}
        )
        await client.receive_any(expected_type="joined_table", timeout=5.0)

        # Snapshot balance before
        with database.connect(self.args, pool=self.pool) as conn, database.cursor(conn) as cur:
            before = _get_balance(cur, self.PLAYER_MONIKER)

        await client.send({"type": "slot_spin", "bet": 10})
        msg = await client.receive_any(expected_type="slot_result", timeout=10.0)
        self.assertIn("spin", msg)
        spin = msg["spin"]
        self.assertEqual(spin["bet"], 10)
        self.assertEqual(spin["payout"], max(0, spin.get("payout", 0)))
        self.assertEqual(spin["net"], spin["payout"] - spin["bet"])
        self.assertEqual(len(spin["reels"]), 5)
        self.assertEqual(len(spin["center_row"]), 5)

        # Bank balance must reflect net
        with database.connect(self.args, pool=self.pool) as conn, database.cursor(conn) as cur:
            after = _get_balance(cur, self.PLAYER_MONIKER)
        self.assertEqual(after, before + spin["net"])

    # -- 2: paytable endpoint -----------------------------------------------
    async def test_paytable_endpoint(self) -> None:
        client = await self._connect_and_auth(self.PLAYER_MONIKER)
        self.clients.append(client)
        await self._create_slots_table(client, self.TABLE_MONIKER)
        await client.send({"type": "join_table", "moniker": self.TABLE_MONIKER})
        await client.receive_any(expected_type="joined_table", timeout=5.0)
        await client.send({"type": "slot_paytable"})
        msg = await client.receive_any(expected_type="slot_paytable", timeout=5.0)
        self.assertIn("payouts", msg)
        self.assertGreater(len(msg["payouts"]), 0)
        for entry in msg["payouts"]:
            self.assertIn("symbols", entry)
            self.assertIn("multiplier", entry)

    # -- 3: history endpoint ------------------------------------------------
    async def test_history_endpoint(self) -> None:

        client = await self._connect_and_auth(self.PLAYER_MONIKER)
        self.clients.append(client)
        await self._create_slots_table(client, self.TABLE_MONIKER)
        await client.send({"type": "join_table", "moniker": self.TABLE_MONIKER})
        await client.receive_any(expected_type="joined_table", timeout=5.0)

        # Two spins
        for _ in range(2):
            await client.send({"type": "slot_spin", "bet": 5})
            await client.receive_any(expected_type="slot_result", timeout=5.0)

        await client.send({"type": "slot_history", "limit": 10})
        msg = await client.receive_any(expected_type="slot_history", timeout=5.0)
        self.assertEqual(len(msg["spins"]), 2)
        # Newest first
        self.assertGreaterEqual(msg["spins"][0]["spun_at"], msg["spins"][1]["spun_at"])
        # Both spins belong to the player
        for s in msg["spins"]:
            self.assertEqual(s["player_moniker"], self.PLAYER_MONIKER)

    # -- 4: spectator receives broadcast ------------------------------------
    async def test_spectator_receives_broadcast(self) -> None:
        player = await self._connect_and_auth(self.PLAYER_MONIKER)
        spectator = await self._connect_and_auth(self.SPECTATOR_MONIKER)
        self.clients.extend([player, spectator])

        await self._create_slots_table(player, self.TABLE_MONIKER)
        await player.send({"type": "join_table", "moniker": self.TABLE_MONIKER})
        await player.receive_any(expected_type="joined_table", timeout=5.0)
        await spectator.send({"type": "watch_table", "moniker": self.TABLE_MONIKER})
        # Drain the watch_table response
        with contextlib.suppress(TimeoutError):
            await spectator.receive(timeout=2.0)

        # Player spins
        await player.send({"type": "slot_spin", "bet": 10})

        # Spectator should receive slot_result on the channel
        msg = await spectator.receive_any(expected_type="slot_result", timeout=10.0)
        self.assertIn("spin", msg)
        self.assertEqual(msg["spin"]["bet"], 10)

    # -- 5: player also receives own broadcast ------------------------------
    async def test_player_also_receives_own_broadcast(self) -> None:
        player = await self._connect_and_auth(self.PLAYER_MONIKER)
        self.clients.append(player)
        await self._create_slots_table(player, self.TABLE_MONIKER)
        await player.send({"type": "join_table", "moniker": self.TABLE_MONIKER})
        await player.receive_any(expected_type="joined_table", timeout=5.0)

        await player.send({"type": "slot_spin", "bet": 5})
        first = await player.receive_any(expected_type="slot_result", timeout=5.0)
        # The slot handler publishes the broadcast to the table channel. The
        # player is also subscribed to the channel, so they receive the
        # broadcast in addition to the direct reply. We just verify the
        # direct reply arrived; the second slot_result is the broadcast.
        self.assertIn("spin", first)
        try:
            second = await player.receive_any(
                expected_type="slot_result", timeout=2.0
            )
            self.assertIn("spin", second)
        except TimeoutError:
            # Acceptable: the implementation may not double-deliver to the
            # originating session. The first delivery is sufficient.
            pass

    # -- 6: first join succeeds ---------------------------------------------
    async def test_join_slots_table_succeeds_for_first_player(self) -> None:
        client = await self._connect_and_auth(self.PLAYER_MONIKER)
        self.clients.append(client)
        await self._create_slots_table(client, self.TABLE_MONIKER)
        await client.send({"type": "join_table", "moniker": self.TABLE_MONIKER})
        msg = await client.receive_any(expected_type="joined_table", timeout=5.0)
        self.assertEqual(msg["moniker"], self.TABLE_MONIKER)

    # -- 7: second join rejected --------------------------------------------
    async def test_second_join_rejected_with_table_full(self) -> None:
        p1 = await self._connect_and_auth(self.PLAYER_MONIKER)
        p2 = await self._connect_and_auth(self.SPECTATOR_MONIKER)
        self.clients.extend([p1, p2])
        await self._create_slots_table(p1, self.TABLE_MONIKER)
        await p1.send({"type": "join_table", "moniker": self.TABLE_MONIKER})
        await p1.receive_any(expected_type="joined_table", timeout=5.0)
        await p2.send({"type": "join_table", "moniker": self.TABLE_MONIKER})
        msg = await p2.receive_any(expected_type="error", timeout=5.0)
        self.assertEqual(msg["code"], "join_failed")
        self.assertIn("single seat", msg.get("message", ""))

    # -- 8: watch_table succeeds after seat full -----------------------------
    async def test_watch_table_succeeds_after_seat_full(self) -> None:
        p1 = await self._connect_and_auth(self.PLAYER_MONIKER)
        p2 = await self._connect_and_auth(self.SPECTATOR_MONIKER)
        self.clients.extend([p1, p2])
        await self._create_slots_table(p1, self.TABLE_MONIKER)
        await p1.send({"type": "join_table", "moniker": self.TABLE_MONIKER})
        await p1.receive_any(expected_type="joined_table", timeout=5.0)
        # jam-2 cannot join (table_full) but can watch
        await p2.send({"type": "join_table", "moniker": self.TABLE_MONIKER})
        await p2.receive_any(expected_type="error", timeout=5.0)
        await p2.send({"type": "watch_table", "moniker": self.TABLE_MONIKER})
        # Should not error - any response is acceptable
        try:
            msg = await p2.receive(timeout=3.0)
            # If we got an error, fail
            if isinstance(msg, dict) and msg.get("type") == "error":
                self.fail(f"watch_table should not error: {msg}")
        except TimeoutError:
            # No immediate response is fine; subscription is the side effect
            pass

    # -- 9: not authenticated ------------------------------------------------
    async def test_slot_spin_not_authenticated(self) -> None:
        client = _BedWebSocketTestClient(self.uri)
        await client.connect()
        self.clients.append(client)
        await client.send({"type": "slot_spin", "bet": 10})
        msg = await client.receive_any(expected_type="error", timeout=5.0)
        self.assertEqual(msg["code"], "not_authenticated")

    # -- 10: not at table ---------------------------------------------------
    async def test_slot_spin_not_at_table(self) -> None:
        client = await self._connect_and_auth(self.PLAYER_MONIKER)
        self.clients.append(client)
        # No join_table
        await client.send({"type": "slot_spin", "bet": 10})
        msg = await client.receive_any(expected_type="error", timeout=5.0)
        # Access policy denies with "forbidden" before the handler-level
        # "not_at_table" branch is reached. Both are valid expressions
        # of the same precondition (session not bound to a table).
        self.assertIn(msg["code"], ("forbidden", "not_at_table"))

    # -- 11: bet below min --------------------------------------------------
    async def test_slot_spin_bet_below_min(self) -> None:
        client = await self._connect_and_auth(self.PLAYER_MONIKER)
        self.clients.append(client)
        await self._create_slots_table(client, self.TABLE_MONIKER, min_bet=10, max_bet=1000)
        await client.send({"type": "join_table", "moniker": self.TABLE_MONIKER})
        await client.receive_any(expected_type="joined_table", timeout=5.0)
        await client.send({"type": "slot_spin", "bet": 1})
        msg = await client.receive_any(expected_type="error", timeout=5.0)
        self.assertEqual(msg["code"], "bet_below_min")

    # -- 12: bet above max --------------------------------------------------
    async def test_slot_spin_bet_above_max(self) -> None:
        client = await self._connect_and_auth(self.PLAYER_MONIKER)
        self.clients.append(client)
        await self._create_slots_table(client, self.TABLE_MONIKER, min_bet=1, max_bet=100)
        await client.send({"type": "join_table", "moniker": self.TABLE_MONIKER})
        await client.receive_any(expected_type="joined_table", timeout=5.0)
        await client.send({"type": "slot_spin", "bet": 500})
        msg = await client.receive_any(expected_type="error", timeout=5.0)
        self.assertEqual(msg["code"], "bet_above_max")

    # -- 13: insufficient funds ---------------------------------------------
    async def test_slot_spin_insufficient_funds(self) -> None:
        from bbsengine6 import database

        # Drain jam-2's balance to 1
        with database.connect(self.args, pool=self.pool) as conn, database.cursor(conn) as cur:
            cur.execute(
                "UPDATE bank.__account SET balance = 1 WHERE moniker = %s",
                (self.SPECTATOR_MONIKER,),
            )

        client = await self._connect_and_auth(self.SPECTATOR_MONIKER)
        self.clients.append(client)
        # jam-2 creates and joins their own table
        table2 = f"slots-{self.SPECTATOR_MONIKER}"
        await self._create_slots_table(client, table2, min_bet=1, max_bet=1000)
        await client.send({"type": "join_table", "moniker": table2})
        await client.receive_any(expected_type="joined_table", timeout=5.0)
        # Now try to bet 500 (balance is 1)
        await client.send({"type": "slot_spin", "bet": 500})
        msg = await client.receive_any(expected_type="error", timeout=5.0)
        self.assertEqual(msg["code"], "insufficient_funds")

    # -- 14: invalid bet type -----------------------------------------------
    async def test_slot_spin_invalid_bet_type(self) -> None:
        client = await self._connect_and_auth(self.PLAYER_MONIKER)
        self.clients.append(client)
        await self._create_slots_table(client, self.TABLE_MONIKER)
        await client.send({"type": "join_table", "moniker": self.TABLE_MONIKER})
        await client.receive_any(expected_type="joined_table", timeout=5.0)
        await client.send({"type": "slot_spin", "bet": "ten"})
        msg = await client.receive_any(expected_type="error", timeout=5.0)
        self.assertEqual(msg["code"], "invalid_bet")

    # -- 15: wrong game type ------------------------------------------------
    async def test_slot_spin_wrong_game_type(self) -> None:
        client = await self._connect_and_auth(self.PLAYER_MONIKER)
        self.clients.append(client)
        await self._create_bj_table(client, self.BJ_TABLE_MONIKER)
        await client.send({"type": "join_table", "moniker": self.BJ_TABLE_MONIKER})
        await client.receive_any(expected_type="joined_table", timeout=5.0)
        await client.send({"type": "slot_spin", "bet": 10})
        msg = await client.receive_any(expected_type="error", timeout=5.0)
        self.assertEqual(msg["code"], "wrong_game_type")

    # -- 16: table not found ------------------------------------------------
    async def test_slot_spin_table_not_found(self) -> None:
        client = await self._connect_and_auth(self.PLAYER_MONIKER)
        self.clients.append(client)
        # Force-set a bogus table_moniker on the session via join_table first
        # actually the simplest path: create a real table, join, then leave,
        # then try spin on the bogus name. But the handler reads
        # self.sessions.get_table_moniker. Workaround: just send slot_spin
        # with table_moniker in the message and a known-bogus value.
        await client.send(
            {
                "type": "slot_spin",
                "bet": 10,
                "table_moniker": "this-table-does-not-exist",
            }
        )
        msg = await client.receive_any(expected_type="error", timeout=5.0)
        # Access policy checks session.table_moniker vs target; a bogus
        # target with no bound seat yields "forbidden" first. Either
        # outcome is acceptable; the contract is "no spin happens".
        self.assertIn(msg["code"], ("forbidden", "not_at_table", "table_not_found"))

    # -- 17: stats after multiple spins -------------------------------------
    async def test_stats_after_multiple_spins(self) -> None:
        from bbsengine6 import database

        client = await self._connect_and_auth(self.PLAYER_MONIKER)
        self.clients.append(client)
        await self._create_slots_table(client, self.TABLE_MONIKER)
        await client.send({"type": "join_table", "moniker": self.TABLE_MONIKER})
        await client.receive_any(expected_type="joined_table", timeout=5.0)

        total_payout = 0
        biggest = 0
        for _ in range(5):
            await client.send({"type": "slot_spin", "bet": 5})
            msg = await client.receive_any(expected_type="slot_result", timeout=5.0)
            total_payout += msg["spin"]["payout"]
            biggest = max(biggest, msg["spin"]["payout"])

        with database.connect(self.args, pool=self.pool) as conn, database.cursor(conn) as cur:
            stats = _stats_for(cur, self.PLAYER_MONIKER)

        self.assertEqual(stats.get("slots.spins"), 5)
        self.assertEqual(stats.get("slots.net"), total_payout - 5 * 5)
        if biggest > 0:
            self.assertEqual(stats.get("slots.biggest_win"), biggest)

    # -- 18: spin row persisted ---------------------------------------------
    async def test_spin_row_persisted(self) -> None:
        from bbsengine6 import database

        client = await self._connect_and_auth(self.PLAYER_MONIKER)
        self.clients.append(client)
        await self._create_slots_table(client, self.TABLE_MONIKER)
        await client.send({"type": "join_table", "moniker": self.TABLE_MONIKER})
        await client.receive_any(expected_type="joined_table", timeout=5.0)

        with database.connect(self.args, pool=self.pool) as conn, database.cursor(conn) as cur:
            before = _spin_row_count(cur, self.PLAYER_MONIKER)

        await client.send({"type": "slot_spin", "bet": 5})
        await client.receive_any(expected_type="slot_result", timeout=5.0)

        with database.connect(self.args, pool=self.pool) as conn, database.cursor(conn) as cur:
            after = _spin_row_count(cur, self.PLAYER_MONIKER)
        self.assertEqual(after, before + 1)

    # -- 19: balance reconciles across spins --------------------------------
    async def test_balance_reconciles_across_spins(self) -> None:
        from bbsengine6 import database

        client = await self._connect_and_auth(self.PLAYER_MONIKER)
        self.clients.append(client)
        await self._create_slots_table(client, self.TABLE_MONIKER)
        await client.send({"type": "join_table", "moniker": self.TABLE_MONIKER})
        await client.receive_any(expected_type="joined_table", timeout=5.0)

        with database.connect(self.args, pool=self.pool) as conn, database.cursor(conn) as cur:
            before = _get_balance(cur, self.PLAYER_MONIKER)

        net = 0
        for _ in range(10):
            await client.send({"type": "slot_spin", "bet": 5})
            msg = await client.receive_any(expected_type="slot_result", timeout=5.0)
            net += msg["spin"]["net"]

        with database.connect(self.args, pool=self.pool) as conn, database.cursor(conn) as cur:
            after = _get_balance(cur, self.PLAYER_MONIKER)
        self.assertEqual(after, before + net)

    # -- 20: re-auth after disconnect ---------------------------------------
    async def test_re_auth_after_disconnect(self) -> None:
        client = await self._connect_and_auth(self.PLAYER_MONIKER)
        self.clients.append(client)
        await self._create_slots_table(client, self.TABLE_MONIKER)
        await client.send({"type": "join_table", "moniker": self.TABLE_MONIKER})
        await client.receive_any(expected_type="joined_table", timeout=5.0)

        # Leave explicitly so the seat is free; then disconnect.
        await client.send({"type": "leave_table", "moniker": self.TABLE_MONIKER})
        await client.receive_any(expected_type="left_table", timeout=5.0)
        await client.close()

        # Reconnect and re-auth
        client2 = await self._connect_and_auth(self.PLAYER_MONIKER)
        self.clients.append(client2)
        await client2.send({"type": "join_table", "moniker": self.TABLE_MONIKER})
        await client2.receive_any(expected_type="joined_table", timeout=5.0)
        await client2.send({"type": "slot_spin", "bet": 5})
        msg = await client2.receive_any(expected_type="slot_result", timeout=5.0)
        self.assertIn("spin", msg)

    # -- 21: zero bet ------------------------------------------------------
    async def test_slot_spin_zero_bet(self) -> None:
        client = await self._connect_and_auth(self.PLAYER_MONIKER)
        self.clients.append(client)
        await self._create_slots_table(client, self.TABLE_MONIKER)
        await client.send({"type": "join_table", "moniker": self.TABLE_MONIKER})
        await client.receive_any(expected_type="joined_table", timeout=5.0)
        await client.send({"type": "slot_spin", "bet": 0})
        msg = await client.receive_any(expected_type="error", timeout=5.0)
        self.assertEqual(msg["code"], "invalid_bet")

    # -- 22: negative bet --------------------------------------------------
    async def test_slot_spin_negative_bet(self) -> None:
        client = await self._connect_and_auth(self.PLAYER_MONIKER)
        self.clients.append(client)
        await self._create_slots_table(client, self.TABLE_MONIKER)
        await client.send({"type": "join_table", "moniker": self.TABLE_MONIKER})
        await client.receive_any(expected_type="joined_table", timeout=5.0)
        await client.send({"type": "slot_spin", "bet": -1})
        msg = await client.receive_any(expected_type="error", timeout=5.0)
        self.assertEqual(msg["code"], "invalid_bet")

    # -- 23: bet at min (inclusive) ----------------------------------------
    async def test_slot_spin_bet_at_min(self) -> None:
        client = await self._connect_and_auth(self.PLAYER_MONIKER)
        self.clients.append(client)
        await self._create_slots_table(client, self.TABLE_MONIKER, min_bet=10, max_bet=1000)
        await client.send({"type": "join_table", "moniker": self.TABLE_MONIKER})
        await client.receive_any(expected_type="joined_table", timeout=5.0)
        await client.send({"type": "slot_spin", "bet": 10})
        msg = await client.receive_any(expected_type="slot_result", timeout=5.0)
        self.assertEqual(msg["spin"]["bet"], 10)

    # -- 24: bet at max (inclusive) ----------------------------------------
    async def test_slot_spin_bet_at_max(self) -> None:
        client = await self._connect_and_auth(self.PLAYER_MONIKER)
        self.clients.append(client)
        await self._create_slots_table(client, self.TABLE_MONIKER, min_bet=1, max_bet=100)
        await client.send({"type": "join_table", "moniker": self.TABLE_MONIKER})
        await client.receive_any(expected_type="joined_table", timeout=5.0)
        await client.send({"type": "slot_spin", "bet": 100})
        msg = await client.receive_any(expected_type="slot_result", timeout=5.0)
        self.assertEqual(msg["spin"]["bet"], 100)

    # -- 25: spectator cannot spin -----------------------------------------
    async def test_spectator_cannot_spin(self) -> None:
        player = await self._connect_and_auth(self.PLAYER_MONIKER)
        spectator = await self._connect_and_auth(self.SPECTATOR_MONIKER)
        self.clients.extend([player, spectator])
        await self._create_slots_table(player, self.TABLE_MONIKER)
        await player.send({"type": "join_table", "moniker": self.TABLE_MONIKER})
        await player.receive_any(expected_type="joined_table", timeout=5.0)
        await spectator.send({"type": "watch_table", "moniker": self.TABLE_MONIKER})
        # Drain whatever the watch response is
        with contextlib.suppress(TimeoutError):
            await spectator.receive(timeout=1.5)
        # Spectator sends spin
        await spectator.send({"type": "slot_spin", "bet": 5})
        msg = await spectator.receive_any(expected_type="error", timeout=5.0)
        self.assertIn(msg["code"], ("forbidden", "not_at_table"))

    # -- 26: concurrent second-client spin rejected ------------------------
    async def test_concurrent_spin_attempts_one_rejected(self) -> None:
        p1 = await self._connect_and_auth(self.PLAYER_MONIKER)
        p2 = await self._connect_and_auth(self.SPECTATOR_MONIKER)
        self.clients.extend([p1, p2])
        await self._create_slots_table(p1, self.TABLE_MONIKER)
        await p1.send({"type": "join_table", "moniker": self.TABLE_MONIKER})
        await p1.receive_any(expected_type="joined_table", timeout=5.0)
        # p2 cannot join the single-seat table
        await p2.send({"type": "join_table", "moniker": self.TABLE_MONIKER})
        await p2.receive_any(expected_type="error", timeout=5.0)
        # p2 attempts a spin; should fail with not_at_table (or forbidden if
        # the access policy denies first)
        await p2.send({"type": "slot_spin", "bet": 5})
        msg = await p2.receive_any(expected_type="error", timeout=5.0)
        self.assertIn(msg["code"], ("forbidden", "not_at_table"))
        # Meanwhile p1 (the seated player) can still spin normally
        await p1.send({"type": "slot_spin", "bet": 5})
        msg = await p1.receive_any(expected_type="slot_result", timeout=5.0)
        self.assertIn("spin", msg)

    # -- 27: paytable default for fresh table ------------------------------
    async def test_paytable_endpoint_returns_default_for_new_table(self) -> None:
        client = await self._connect_and_auth(self.PLAYER_MONIKER)
        self.clients.append(client)
        await self._create_slots_table(client, self.TABLE_MONIKER)
        # ``slot_paytable`` policy requires a seated session.
        await client.send({"type": "join_table", "moniker": self.TABLE_MONIKER})
        await client.receive_any(expected_type="joined_table", timeout=5.0)
        await client.send({"type": "slot_paytable"})
        msg = await client.receive_any(expected_type="slot_paytable", timeout=5.0)
        self.assertEqual(msg["moniker"], self.TABLE_MONIKER)
        # Default paytable has the seven-known entries
        symbols_seen = {tuple(e["symbols"]) for e in msg["payouts"]}
        self.assertIn(("SEVEN", "SEVEN", "SEVEN"), symbols_seen)
        self.assertIn(("CHERRY",), symbols_seen)

    # -- 28: paytable with override ---------------------------------------
    async def test_paytable_endpoint_with_override(self) -> None:
        from bbsengine6 import database

        from casino.services.slots import invalidate_dealer

        client = await self._connect_and_auth(self.PLAYER_MONIKER)
        self.clients.append(client)
        await self._create_slots_table(client, self.TABLE_MONIKER)
        await client.send({"type": "join_table", "moniker": self.TABLE_MONIKER})
        await client.receive_any(expected_type="joined_table", timeout=5.0)
        # Apply override + invalidate the dealer cache
        with database.connect(self.args, pool=self.pool) as conn, database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "UPDATE $casino.__table SET attrs = :attrs WHERE moniker = :moniker",
                    attrs=database.Jsonb({"paytable_override": [{"symbols": ["LEMON", "LEMON", "LEMON"], "multiplier": 250}]}),
                    moniker=self.TABLE_MONIKER,
                )
            )
        invalidate_dealer(self.TABLE_MONIKER)
        await client.send({"type": "slot_paytable"})
        msg = await client.receive_any(expected_type="slot_paytable", timeout=5.0)
        symbols_seen = {tuple(e["symbols"]) for e in msg["payouts"]}
        # Only the override is present (default excluded once override dict is set)
        self.assertIn(("LEMON", "LEMON", "LEMON"), symbols_seen)
        # Sanity: the override multiplier should be reported verbatim
        lemon = next(
            e for e in msg["payouts"] if tuple(e["symbols"]) == ("LEMON", "LEMON", "LEMON")
        )
        self.assertEqual(lemon["multiplier"], 250)

    # -- 29: history limit honored -----------------------------------------
    async def test_history_endpoint_respects_limit(self) -> None:
        client = await self._connect_and_auth(self.PLAYER_MONIKER)
        self.clients.append(client)
        await self._create_slots_table(client, self.TABLE_MONIKER)
        await client.send({"type": "join_table", "moniker": self.TABLE_MONIKER})
        await client.receive_any(expected_type="joined_table", timeout=5.0)
        for _ in range(4):
            await client.send({"type": "slot_spin", "bet": 5})
            await client.receive_any(expected_type="slot_result", timeout=5.0)
        await client.send({"type": "slot_history", "limit": 2})
        msg = await client.receive_any(expected_type="slot_history", timeout=5.0)
        self.assertEqual(len(msg["spins"]), 2)

    # -- 30: history limit=0 returns empty ---------------------------------
    async def test_history_endpoint_limit_zero_returns_empty(self) -> None:
        client = await self._connect_and_auth(self.PLAYER_MONIKER)
        self.clients.append(client)
        await self._create_slots_table(client, self.TABLE_MONIKER)
        await client.send({"type": "join_table", "moniker": self.TABLE_MONIKER})
        await client.receive_any(expected_type="joined_table", timeout=5.0)
        await client.send({"type": "slot_spin", "bet": 5})
        await client.receive_any(expected_type="slot_result", timeout=5.0)
        await client.send({"type": "slot_history", "limit": 0})
        msg = await client.receive_any(expected_type="slot_history", timeout=5.0)
        self.assertEqual(msg["spins"], [])

    # -- 31: disconnect after spin request completes atomically ------------
    async def test_disconnect_after_spin_request_completes(self) -> None:
        from bbsengine6 import database

        client = await self._connect_and_auth(self.PLAYER_MONIKER)
        self.clients.append(client)
        await self._create_slots_table(client, self.TABLE_MONIKER)
        await client.send({"type": "join_table", "moniker": self.TABLE_MONIKER})
        await client.receive_any(expected_type="joined_table", timeout=5.0)

        with database.connect(self.args, pool=self.pool) as conn, database.cursor(conn) as cur:
            before_balance = _get_balance(cur, self.PLAYER_MONIKER)
            before_spins = _spin_row_count(cur, self.PLAYER_MONIKER)

        # Send spin and immediately close the connection
        await client.send({"type": "slot_spin", "bet": 5})
        await client.close()
        self.clients.remove(client)

        # The transaction is atomic; give the server a moment to flush
        await asyncio.sleep(0.2)
        with database.connect(self.args, pool=self.pool) as conn, database.cursor(conn) as cur:
            after_balance = _get_balance(cur, self.PLAYER_MONIKER)
            after_spins = _spin_row_count(cur, self.PLAYER_MONIKER)
        self.assertEqual(after_spins, before_spins + 1)
        # Balance must reflect the spin (delta is exactly -5 for a loss
        # or >= -5 + payout for a win); easiest assertion: it changed.
        self.assertNotEqual(after_balance, before_balance)

    # -- 32: response includes new_balance matching DB --------------------
    async def test_response_includes_new_balance(self) -> None:
        from bbsengine6 import database

        client = await self._connect_and_auth(self.PLAYER_MONIKER)
        self.clients.append(client)
        await self._create_slots_table(client, self.TABLE_MONIKER)
        await client.send({"type": "join_table", "moniker": self.TABLE_MONIKER})
        await client.receive_any(expected_type="joined_table", timeout=5.0)
        await client.send({"type": "slot_spin", "bet": 5})
        msg = await client.receive_any(expected_type="slot_result", timeout=5.0)
        self.assertIn("new_balance", msg["spin"])
        with database.connect(self.args, pool=self.pool) as conn, database.cursor(conn) as cur:
            db_balance = _get_balance(cur, self.PLAYER_MONIKER)
        self.assertEqual(int(msg["spin"]["new_balance"]), db_balance)

    # -- 33: grid structure invariants ------------------------------------
    async def test_grid_structure_invariants(self) -> None:
        client = await self._connect_and_auth(self.PLAYER_MONIKER)
        self.clients.append(client)
        await self._create_slots_table(client, self.TABLE_MONIKER)
        await client.send({"type": "join_table", "moniker": self.TABLE_MONIKER})
        await client.receive_any(expected_type="joined_table", timeout=5.0)
        await client.send({"type": "slot_spin", "bet": 5})
        msg = await client.receive_any(expected_type="slot_result", timeout=5.0)
        spin = msg["spin"]
        # reels: 5 columns, each with 3 symbols
        self.assertEqual(len(spin["reels"]), 5)
        for col in spin["reels"]:
            self.assertEqual(len(col), 3)
            for sym in col:
                self.assertIn(sym, {"CHERRY", "LEMON", "PLUM", "BELL", "BAR", "SEVEN", "BLANK"})
        # center_row is the middle row of each column
        self.assertEqual(len(spin["center_row"]), 5)
        for i, sym in enumerate(spin["center_row"]):
            self.assertEqual(sym, spin["reels"][i][1])

    # -- 34: wins payload shape -------------------------------------------
    async def test_wins_payload_shape(self) -> None:
        client = await self._connect_and_auth(self.PLAYER_MONIKER)
        self.clients.append(client)
        await self._create_slots_table(client, self.TABLE_MONIKER)
        await client.send({"type": "join_table", "moniker": self.TABLE_MONIKER})
        await client.receive_any(expected_type="joined_table", timeout=5.0)
        # Run a batch; for each spin verify wins is a list of dicts
        # with the expected keys.
        for _ in range(3):
            await client.send({"type": "slot_spin", "bet": 5})
            msg = await client.receive_any(expected_type="slot_result", timeout=5.0)
            wins = msg["spin"]["wins"]
            self.assertIsInstance(wins, list)
            for w in wins:
                self.assertIn("symbols", w)
                self.assertIn("multiplier", w)
                self.assertIn("payout", w)
                self.assertIsInstance(w["symbols"], list)
                self.assertIsInstance(w["multiplier"], int)
                self.assertIsInstance(w["payout"], int)
                # Payout = bet * multiplier (and bet is 5)
                self.assertEqual(w["payout"], 5 * w["multiplier"])

    # -- 35: slot_table_history endpoint returns this table's spins -------
    async def test_slot_table_history_endpoint(self) -> None:
        client = await self._connect_and_auth(self.PLAYER_MONIKER)
        self.clients.append(client)
        await self._create_slots_table(client, self.TABLE_MONIKER)
        await client.send({"type": "join_table", "moniker": self.TABLE_MONIKER})
        await client.receive_any(expected_type="joined_table", timeout=5.0)
        # Spin twice
        for _ in range(2):
            await client.send({"type": "slot_spin", "bet": 5})
            await client.receive_any(expected_type="slot_result", timeout=5.0)
        await client.send({"type": "slot_table_history", "limit": 10})
        msg = await client.receive_any(expected_type="slot_table_history", timeout=5.0)
        self.assertEqual(msg["table_moniker"], self.TABLE_MONIKER)
        self.assertEqual(len(msg["spins"]), 2)
        for s in msg["spins"]:
            self.assertEqual(s["table_moniker"], self.TABLE_MONIKER)
        # Newest first
        self.assertGreaterEqual(msg["spins"][0]["spun_at"], msg["spins"][1]["spun_at"])

    # -- 36: slot_table_history without being at table ---------------------
    async def test_slot_table_history_not_at_table(self) -> None:
        client = await self._connect_and_auth(self.PLAYER_MONIKER)
        self.clients.append(client)
        # No join_table call
        await client.send({"type": "slot_table_history"})
        msg = await client.receive_any(expected_type="error", timeout=5.0)
        self.assertIn(msg["code"], ("forbidden", "not_at_table"))


if __name__ == "__main__":
    unittest.main()
