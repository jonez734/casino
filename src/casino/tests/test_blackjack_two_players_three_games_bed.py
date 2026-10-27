#!/usr/bin/env python3
# casino/tests/test_blackjack_two_players_three_games_bed.py
# Bed-targeted companion to test_blackjack_two_players_three_games.py.
#
# Connects to a running bed daemon (default ws://127.0.0.1:8765/),
# authenticates as ``jam`` (pre-existing bed member) and a second
# member created via ``bbsengine6.console.member.add`` (which also
# creates the postgres role needed for ``join_table`` / ``bet``), and
# plays 3 complete hands of blackjack end-to-end over the wire.
#
# Skipped when bed is not reachable so it can sit in the test suite
# without breaking local CI runs that don't have bed running.
#
# IMPORTANT: bed loads casino modules at startup. After pulling new
# casino source you MUST restart the bed daemon for the new code to
# take effect -- Python does not auto-reload modules in a running
# process. Without a restart, the duplicate-table test will fail
# with a unique-constraint violation on
# ``casino.__bank_table_pkey`` and any test that depends on the
# channel-publish fix in ``bbsengine6.net.transport.channel_publish``
# will silently fail because the broadcast is dropped on the old
# path-based code path.
#
# Env overrides:
#   CASINO_TEST_BED_URI  (default: ws://127.0.0.1:8765/)
#   CASINO_TEST_BED_DATABASE  (default: zoid6)

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import sys
import time
import unittest
import uuid
from typing import Optional
from unittest.mock import patch

import pytest
import websockets

sys.path.insert(0, "/home/opencode/data/work/casino/src")
sys.path.insert(0, "/home/opencode/data/work/bbsengine6/py/src")
sys.path.insert(0, "/home/opencode/data/work/bed/src")

from casino.tests import _dbname

# Opt-in only. The port 8765 daemon is the live zoid6 bed; these tests log in and bet through it.
# Set CASINO_TEST_BED_URI to a bed started against zoid6test to run them. Reachability is not enough.
BED_URI = os.environ.get("CASINO_TEST_BED_URI", "")
BED_ENABLED = bool(BED_URI)
BED_DATABASE = _dbname.current_dbname()
TEST_TABLE_PREFIX = "blackjack-bed-2p-"
DEFAULT_TIMEOUT_S = 10.0
PING_INTERVAL = 30.0
BET_AMOUNT = 10
NUM_HANDS = 3


# ----- bed probe ------------------------------------------------------------



_SKIP_REASON = (
    "bed-daemon test is opt-in: set CASINO_TEST_BED_URI to a bed started against zoid6test"
)


# ----- websocket client -----------------------------------------------------


class WebSocketTestClient:
    """Minimal WebSocket test client with a receive queue."""

    def __init__(self, uri: str, timeout: float = DEFAULT_TIMEOUT_S):
        self.uri = uri
        self.timeout = timeout
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self._rx: asyncio.Queue = asyncio.Queue()
        self._token: Optional[str] = None
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def connect(self) -> None:
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
        self._task = asyncio.create_task(self._pump())

    async def _pump(self) -> None:
        try:
            async for raw in self.ws:
                if not self._running:
                    break
                try:
                    msg = json.loads(raw)
                    # Keep the login token from auth_result; the live bed requires it on each op.
                    if msg.get("type") == "auth_result" and msg.get("token"):
                        self._token = msg["token"]
                    await self._rx.put(msg)
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass
        finally:
            self._running = False

    async def send(self, payload: dict) -> None:
        if not self.ws or not self._running:
            raise ConnectionError("not connected")
        if getattr(self, "_token", None) and "token" not in payload:
            payload = {**payload, "token": self._token}
        await self.ws.send(json.dumps(payload))

    async def recv(self, timeout: Optional[float] = None) -> dict:
        return await asyncio.wait_for(
            self._rx.get(), timeout=timeout or self.timeout
        )

    async def receive_messages(self, max_count: int = 20, timeout: float = 5.0) -> list:
        messages: list = []
        deadline = asyncio.get_event_loop().time() + timeout
        for _ in range(max_count):
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                break
            try:
                msg = await asyncio.wait_for(
                    self._rx.get(), timeout=min(remaining, 0.5)
                )
                messages.append(msg)
            except asyncio.TimeoutError:
                break
        return messages

    async def close(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
        if self.ws:
            with contextlib.suppress(Exception):
                await self.ws.close(code=1000, reason="Test complete")
        while not self._rx.empty():
            try:
                self._rx.get_nowait()
            except asyncio.QueueEmpty:
                break


# ----- the test -------------------------------------------------------------


LEFTOVER_ROLES_FILE = "/home/opencode/tmp/bjbed_leftover_roles.txt"


def _record_leftover_roles(*names: str) -> None:
    """Append fixture role names to a file that the jam cleanup reads. Never raises."""
    try:
        with open(LEFTOVER_ROLES_FILE, "a", encoding="utf-8") as f:
            for name in names:
                f.write(name + "\n")
    except OSError:
        pass


@pytest.mark.integration
@unittest.skipUnless(BED_ENABLED, _SKIP_REASON)
class TestBlackjackTwoPlayersThreeGamesBed(unittest.IsolatedAsyncioTestCase):
    """``jam`` plus a freshly-created second member play 3 hands of
    blackjack through a running bed daemon.

    ``jam`` is seeded by the bed setup so no member creation is
    needed for it. The second member is created via
    ``bbsengine6.console.member.add`` in ``asyncSetUp`` (which also
    creates the postgres role that ``database.connect`` needs during
    ``join_table`` / ``bet``), and granted the ``sysop`` group so it
    has ``SELECT`` on ``casino.__table`` and friends. The test cleans
    up both members and the casino tables it created in
    ``asyncTearDown``.

    NOTE: a member created via raw SQL INSERT (e.g. ``viewer`` in
    ``test_player_observer.py``) is missing the postgres role, and
    the bed's per-member DB connect in ``join_table`` will then fail
    with ``role '<moniker>' does not exist``. Always use
    ``console.member.add`` for any member that needs to participate
    as a seated player.
    """

    async def asyncSetUp(self) -> None:
        from casino import lib
        from bbsengine6 import database
        from bbsengine6.console import member as con_member

        parser = lib.buildargs()
        args = parser.parse_args(_dbname.dbname_args())
        pool = database.getpool(args)
        with database.connect(args, pool=pool) as conn, database.cursor(conn) as cur:
            cur.execute(
                """
                INSERT INTO bank.__account (moniker, balance, maxtransfer, overdraft_limit)
                VALUES ('casino:house', 0, 1000000, 100000)
                ON CONFLICT (moniker) DO NOTHING
                """
            )

        # Fixtures are installed once by `casino --install-test-data` (see casino.test_data). The
        # test reads their fixed names and the 0600 password file, and creates no members or roles.
        from casino import test_data

        self.moniker_a, self.moniker_b = test_data.FIXTURE_MONIKERS
        passwords = test_data.read_password_file(test_data.password_file_path())
        self.password_a = passwords[self.moniker_a]
        self.password_b = passwords[self.moniker_b]

        self.client_a: Optional[WebSocketTestClient] = None
        self.client_b: Optional[WebSocketTestClient] = None
        self.table_moniker = (
            f"{TEST_TABLE_PREFIX}{int(time.time() * 1000)}"
        )

    async def asyncTearDown(self) -> None:
        from casino import lib
        from bbsengine6 import database

        for client in (self.client_a, self.client_b):
            if client:
                await client.close()

        parser = lib.buildargs()
        args = parser.parse_args(_dbname.dbname_args())
        pool = database.getpool(args)
        with database.connect(args, pool=pool) as conn, database.cursor(conn) as cur:
            cur.execute(
                "DELETE FROM casino.__betlog WHERE cardtablemoniker = %s",
                (self.table_moniker,),
            )
            cur.execute(
                "DELETE FROM casino.__hand "
                "WHERE gameid IN ("
                "SELECT id FROM casino.__game WHERE tablemoniker = %s"
                ")",
                (self.table_moniker,),
            )
            cur.execute(
                "DELETE FROM casino.__game WHERE tablemoniker = %s",
                (self.table_moniker,),
            )
            cur.execute(
                "DELETE FROM casino.map_cardtable_player "
                "WHERE cardtablemoniker = %s",
                (self.table_moniker,),
            )
            cur.execute(
                "DELETE FROM casino.__table WHERE moniker = %s",
                (self.table_moniker,),
            )
            cur.execute(
                "DELETE FROM casino.__bank_table WHERE table_moniker = %s",
                (self.table_moniker,),
            )
            cur.execute(
                "DELETE FROM casino.__bank_player WHERE player_moniker = %s",
                (self.moniker_b,),
            )
            cur.execute(
                "DELETE FROM casino.__player WHERE moniker = %s",
                (self.moniker_b,),
            )
            cur.execute(
                "DELETE FROM bank.__account WHERE moniker = %s",
                (self.moniker_b,),
            )
            cur.execute(
                "DELETE FROM engine.__member WHERE moniker = %s",
                (self.moniker_b,),
            )
            for fixture in (self.moniker_a, self.moniker_b):
                for table_sql in (
                    "DELETE FROM casino.__bank_player WHERE player_moniker = %s",
                    "DELETE FROM casino.__player WHERE moniker = %s",
                    "DELETE FROM bank.__account WHERE moniker = %s",
                    "DELETE FROM engine.__member WHERE moniker = %s",
                ):
                    cur.execute(table_sql, (fixture,))
                # Member creation makes two roles: the OS login role <moniker>, a member of the
                # data role m_<moniker>, and the tracking row. Drop them in dependency order:
                # the login role first (it depends on the data role), then the data role.
                # Member roles are removed by a jam-run cleanup, not here: opencode cannot drop a role
                # another role created (DROP ROLE needs ADMIN OPTION on the target). Record the
                # names so the cleanup can find them.
                _record_leftover_roles(fixture, f"m_{fixture}")
        conn.commit()
        pool.close()

    async def _wait_for_game_state(
        self,
        client: WebSocketTestClient,
        max_messages: int = 20,
        predicate=None,
    ) -> dict:
        messages = await client.receive_messages(max_count=max_messages, timeout=5.0)
        for msg in messages:
            if msg.get("type") != "game_state":
                continue
            if predicate is None or predicate(msg):
                return msg
        self.fail(
            f"No matching game_state received after {max_messages} messages: "
            f"{[m for m in messages if m.get('type') == 'game_state']}"
        )

    async def _wait_for_settled(
        self, client: WebSocketTestClient, max_messages: int = 20
    ) -> dict:
        return await self._wait_for_game_state(
            client,
            max_messages=max_messages,
            predicate=lambda m: m.get("phase") == "settled",
        )

    async def test_two_players_three_hands_through_bed(self) -> None:
        """End-to-end through a running bed + casino router: jam and
        a freshly-created second member sit at a blackjack table,
        both bet, jam stands (which forces the dealer to play for
        both), and we repeat the cycle 3 times. Per hand we verify
        both clients see ``phase=settled`` with the dealer hand
        revealed, and that the dealer hand observed by jam matches
        the one observed by the second member.
        """
        self.client_a = WebSocketTestClient(BED_URI)
        self.client_b = WebSocketTestClient(BED_URI)
        await self.client_a.connect()
        await self.client_b.connect()
        self.assertTrue(self.client_a._running, "jam failed to connect to bed")
        self.assertTrue(self.client_b._running, f"{self.moniker_b} failed to connect to bed")

        await self.client_a.send({"type": "auth", "moniker": self.moniker_a, "password": self.password_a})
        auth_a = await self.client_a.recv()
        self.assertEqual(auth_a.get("type"), "auth_result", f"jam auth reply: {auth_a}")
        self.assertTrue(auth_a.get("success"), f"jam auth success=False: {auth_a}")
        self.assertEqual(auth_a.get("moniker"), self.moniker_a)

        await self.client_b.send(
            {"type": "auth", "moniker": self.moniker_b, "password": self.password_b}
        )
        auth_b = await self.client_b.recv()
        self.assertEqual(
            auth_b.get("type"), "auth_result",
            f"{self.moniker_b} auth reply: {auth_b}",
        )
        self.assertTrue(
            auth_b.get("success"),
            f"{self.moniker_b} auth success=False: {auth_b}",
        )
        self.assertEqual(auth_b.get("moniker"), self.moniker_b)

        await self.client_a.send(
            {
                "type": "create_table",
                "game_type": "blackjack",
                "min_bet": 10,
                "max_bet": 1000,
                "moniker": self.table_moniker,
            }
        )
        created = await self.client_a.recv()
        self.assertEqual(
            created.get("type"), "table_created",
            f"create_table reply: {created}",
        )
        self.assertEqual(created.get("moniker"), self.table_moniker)

        await self.client_a.send({"type": "join_table", "moniker": self.table_moniker})
        joined_a = await self.client_a.recv()
        self.assertEqual(
            joined_a.get("type"), "joined_table",
            f"jam join reply: {joined_a}",
        )

        await self.client_b.send({"type": "join_table", "moniker": self.table_moniker})
        joined_b = await self.client_b.recv()
        self.assertEqual(
            joined_b.get("type"), "joined_table",
            f"{self.moniker_b} join reply: {joined_b}",
        )

        for hand_no in range(1, NUM_HANDS + 1):
            await self.client_a.send({"type": "bet", "amount": BET_AMOUNT})
            game_a_bet = await self._wait_for_game_state(
                self.client_a,
                predicate=lambda m: len(m.get("player_hand", [])) == 2,
            )
            self.assertEqual(
                len(game_a_bet.get("player_hand", [])),
                2,
                f"hand {hand_no}: jam should have 2 cards after bet, "
                f"got {game_a_bet.get('player_hand')}",
            )

            await self.client_b.send({"type": "bet", "amount": BET_AMOUNT})
            game_b_bet = await self._wait_for_game_state(
                self.client_b,
                predicate=lambda m: len(m.get("player_hand", [])) == 2,
            )
            self.assertEqual(
                len(game_b_bet.get("player_hand", [])),
                2,
                f"hand {hand_no}: {self.moniker_b} should have 2 cards after bet, "
                f"got {game_b_bet.get('player_hand')}",
            )

            await self.client_a.send({"type": "stand"})
            settled_a = await self._wait_for_settled(self.client_a)
            settled_b = await self._wait_for_settled(self.client_b)
            self.assertEqual(
                settled_a.get("table_moniker"),
                self.table_moniker,
                f"hand {hand_no}: jam settled game_state must reference the table",
            )
            self.assertEqual(
                settled_b.get("table_moniker"),
                self.table_moniker,
                f"hand {hand_no}: {self.moniker_b} settled game_state must reference the table",
            )
            dealer_a = settled_a.get("dealer_hand", [])
            dealer_b = settled_b.get("dealer_hand", [])
            self.assertNotIn(
                "hidden", dealer_a,
                f"hand {hand_no}: dealer hand should be revealed after stand, "
                f"got jam={dealer_a}",
            )
            self.assertNotIn(
                "hidden", dealer_b,
                f"hand {hand_no}: dealer hand should be revealed after stand, "
                f"got {self.moniker_b}={dealer_b}",
            )
            self.assertGreaterEqual(
                len(dealer_a), 2,
                f"hand {hand_no}: dealer hand should have >=2 cards, got jam={dealer_a}",
            )
            self.assertEqual(
                dealer_a, dealer_b,
                f"hand {hand_no}: jam and {self.moniker_b} must observe the same dealer hand, "
                f"jam={dealer_a} {self.moniker_b}={dealer_b}",
            )


if __name__ == "__main__":
    unittest.main()
