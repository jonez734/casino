#!/usr/bin/env python3
# casino/tests/test_blackjack_two_players_three_games.py
# Integration test: two players (A and B) sit at the same blackjack
# table with the dealer and play 3 complete hands end-to-end over the
# wire. Builds on test_blackjack_multi_user_join.py (which proves both
# players can sit) and adds the full bet -> stand -> dealer-reveal ->
# settled cycle repeated 3 times, plus a database cross-check that
# 3 games and 6 betlog rows were recorded.
#
# Each test run uses a UUID-suffixed moniker triple so concurrent runs
# do not collide. asyncTearDown hard-deletes all test rows.
#
# Note: blackjack's settle_game runs the dealer turn as soon as ANY
# seated player stands, so B's stand after A's stand returns
# ``"No active game"``. We do not require B to explicitly stand; the
# post-A-stand broadcast is what proves the dealer played for both
# players.

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
import unittest
import uuid
from typing import Optional
from unittest.mock import patch

import pytest

sys.path.insert(0, "/home/opencode/data/work/casino/src")

import websockets
from websockets.exceptions import ConnectionClosed

from casino import lib
from casino.api.handler import MessageRouter
from casino.tests import _dbname

DEFAULT_TIMEOUT = 10.0
PING_INTERVAL = 30.0
TEST_PORT = 8769
TEST_URI = f"ws://127.0.0.1:{TEST_PORT}/"
TEST_PASSWORD = "12345"
BET_AMOUNT = 10
NUM_HANDS = 3


class WebSocketTestClient:
    """Minimal WebSocket test client with a receive queue."""

    def __init__(self, uri: str, timeout: float = DEFAULT_TIMEOUT):
        self.uri = uri
        self.timeout = timeout
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self._receive_task: Optional[asyncio.Task] = None
        self._message_queue: asyncio.Queue = asyncio.Queue()
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
        self._receive_task = asyncio.create_task(self._receive_messages())

    async def _receive_messages(self) -> None:
        try:
            async for message in self.ws:
                if not self._running:
                    break
                try:
                    await self._message_queue.put(json.loads(message))
                except json.JSONDecodeError:
                    pass
        except ConnectionClosed:
            pass
        finally:
            self._running = False

    async def send(self, message: dict) -> None:
        if not self.ws or not self._running:
            raise ConnectionError("Not connected")
        await self.ws.send(json.dumps(message))

    async def receive(self, timeout: Optional[float] = None) -> dict:
        return await asyncio.wait_for(
            self._message_queue.get(), timeout=timeout or self.timeout
        )

    async def receive_messages(self, max_count: int = 10, timeout: float = 5.0) -> list:
        messages: list = []
        deadline = asyncio.get_event_loop().time() + timeout
        for _ in range(max_count):
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                break
            try:
                msg = await asyncio.wait_for(
                    self._message_queue.get(), timeout=min(remaining, 0.5)
                )
                messages.append(msg)
            except asyncio.TimeoutError:
                break
        return messages

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
            except asyncio.QueueEmpty:
                break


@pytest.mark.integration
class TestBlackjackTwoPlayersThreeGames(unittest.IsolatedAsyncioTestCase):
    """Two players + dealer play 3 complete hands of blackjack."""

    async def asyncSetUp(self) -> None:
        from bbsengine6 import database
        from bbsengine6.net import WebSocketServer
        from bbsengine6.console import member as con_member

        with contextlib.suppress(Exception):
            await database.reset_async_pool_cache()

        parser = lib.buildargs()
        self.args = parser.parse_args(_dbname.dbname_args())
        self.pool = database.getpool(self.args)

        suffix = uuid.uuid4().hex[:8]
        self.moniker_a = f"bj2p_a_{suffix}"
        self.moniker_b = f"bj2p_b_{suffix}"
        self.table_moniker = f"bj2p_tbl_{suffix}"

        with database.connect(self.args, pool=self.pool) as conn, database.cursor(conn) as cur:
            cur.execute(
                """
                INSERT INTO bank.__account (moniker, balance, maxtransfer, overdraft_limit)
                VALUES ('casino:house', 0, 1000000, 100000)
                ON CONFLICT (moniker) DO NOTHING
                """
            )

        for moniker in (self.moniker_a, self.moniker_b):
            with patch.object(con_member, "_edit") as mock_edit, \
                 patch("bbsengine6.io.inputboolean", return_value=True):
                mock_edit.return_value = {
                    "moniker": moniker,
                    "loginid": moniker,
                    "email": f"{moniker}@test.local",
                    "password": TEST_PASSWORD,
                    "credits": 100000,
                    "ui": ["term"],
                    "attrs": {},
                    "flags": {
                        "APPROVED": {"value": True, "description": "Approved"},
                        "SYSOP": {"value": False, "description": "Sysop"},
                    },
                }
                ok = con_member.add(self.args, pool=self.pool)
                self.assertTrue(
                    ok,
                    f"bbsengine6.console.member.add returned False for {moniker}",
                )

        self.server = WebSocketServer(host="127.0.0.1", port=TEST_PORT)
        self.router = MessageRouter(self.args)
        self.router.register_all(self.server)
        for svc in (
            self.router.table_service,
            self.router.game_service,
            self.router.bet_service,
            self.router.chat_service,
            self.router.slot_service,
        ):
            svc.allow_legacy_session_only = True
        await self.server.start()
        self._server_started = True
        self.client_a: Optional[WebSocketTestClient] = None
        self.client_b: Optional[WebSocketTestClient] = None

    async def asyncTearDown(self) -> None:
        from bbsengine6 import database

        for client in (self.client_a, self.client_b):
            if client:
                await client.close()
        if hasattr(self, "_server_started") and self._server_started:
            with contextlib.suppress(Exception):
                await self.server.stop()

        if hasattr(self, "pool") and self.pool is not None:
            with database.connect(self.args, pool=self.pool) as conn, database.cursor(conn) as cur:
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
                for moniker in (self.moniker_a, self.moniker_b):
                    cur.execute(
                        "DELETE FROM casino.__bank_player WHERE player_moniker = %s",
                        (moniker,),
                    )
                    cur.execute(
                        "DELETE FROM casino.__player WHERE moniker = %s",
                        (moniker,),
                    )
                    cur.execute(
                        "DELETE FROM bank.__account WHERE moniker = %s",
                        (moniker,),
                    )
                    cur.execute(
                        "DELETE FROM engine.__member WHERE moniker = %s",
                        (moniker,),
                    )
            conn.commit()

            self.pool.close()
            self.pool = None

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

    async def test_two_players_three_hands_with_dealer(self) -> None:
        """End-to-end: A and B sit at a blackjack table, both bet, A
        stands (which forces the dealer to play for both), and we
        repeat the cycle 3 times. Each hand we verify:

        - both clients receive a game_state after the bet,
        - both clients see phase=settled and the dealer hand revealed
          after A stands,
        - the dealer hand observed by A matches the one observed by B.

        After all 3 hands we verify the database has 3 settled games
        and 6 betlog entries (A bet + B bet per hand).
        """
        from bbsengine6 import database

        self.client_a = WebSocketTestClient(TEST_URI)
        self.client_b = WebSocketTestClient(TEST_URI)
        await self.client_a.connect()
        await self.client_b.connect()
        self.assertTrue(self.client_a._running, "A failed to connect")
        self.assertTrue(self.client_b._running, "B failed to connect")

        await self.client_a.send(
            {"type": "auth", "moniker": self.moniker_a, "password": TEST_PASSWORD}
        )
        auth_a = await self.client_a.receive()
        self.assertEqual(auth_a["type"], "auth_result", f"A auth reply: {auth_a}")
        self.assertTrue(auth_a["success"], f"A auth success=False: {auth_a}")

        await self.client_b.send(
            {"type": "auth", "moniker": self.moniker_b, "password": TEST_PASSWORD}
        )
        auth_b = await self.client_b.receive()
        self.assertEqual(auth_b["type"], "auth_result", f"B auth reply: {auth_b}")
        self.assertTrue(auth_b["success"], f"B auth success=False: {auth_b}")

        await self.client_a.send(
            {
                "type": "create_table",
                "game_type": "blackjack",
                "min_bet": 10,
                "max_bet": 1000,
                "moniker": self.table_moniker,
            }
        )
        created = await self.client_a.receive()
        self.assertEqual(created["type"], "table_created", f"create_table reply: {created}")

        await self.client_a.send({"type": "join_table", "moniker": self.table_moniker})
        joined_a = await self.client_a.receive()
        self.assertEqual(joined_a["type"], "joined_table", f"A join reply: {joined_a}")

        await self.client_b.send({"type": "join_table", "moniker": self.table_moniker})
        joined_b = await self.client_b.receive()
        self.assertEqual(joined_b["type"], "joined_table", f"B join reply: {joined_b}")

        with database.connect(self.args, pool=self.pool) as conn, database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "SELECT playermoniker FROM $casino.map_cardtable_player "
                    "WHERE cardtablemoniker = :m ORDER BY playermoniker",
                    m=self.table_moniker,
                )
            )
            seated = [row["playermoniker"] for row in cur.fetchall()]
            self.assertEqual(
                sorted(seated),
                sorted([self.moniker_a, self.moniker_b]),
                f"expected both A and B seated, got {seated}",
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
                f"hand {hand_no}: A should have 2 cards after bet, "
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
                f"hand {hand_no}: B should have 2 cards after bet, "
                f"got {game_b_bet.get('player_hand')}",
            )

            await self.client_a.send({"type": "stand"})
            settled_a = await self._wait_for_settled(self.client_a)
            settled_b = await self._wait_for_settled(self.client_b)
            self.assertEqual(
                settled_a.get("table_moniker"),
                self.table_moniker,
                f"hand {hand_no}: A settled game_state must reference the table",
            )
            self.assertEqual(
                settled_b.get("table_moniker"),
                self.table_moniker,
                f"hand {hand_no}: B settled game_state must reference the table",
            )
            dealer_a = settled_a.get("dealer_hand", [])
            dealer_b = settled_b.get("dealer_hand", [])
            self.assertNotIn(
                "hidden",
                dealer_a,
                f"hand {hand_no}: dealer hand should be revealed after stand, "
                f"got A={dealer_a}",
            )
            self.assertNotIn(
                "hidden",
                dealer_b,
                f"hand {hand_no}: dealer hand should be revealed after stand, "
                f"got B={dealer_b}",
            )
            self.assertGreaterEqual(
                len(dealer_a), 2,
                f"hand {hand_no}: dealer hand should have >=2 cards, got A={dealer_a}",
            )
            self.assertEqual(
                dealer_a, dealer_b,
                f"hand {hand_no}: A and B must observe the same dealer hand, "
                f"A={dealer_a} B={dealer_b}",
            )

        with database.connect(self.args, pool=self.pool) as conn, database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "SELECT COUNT(*) AS n FROM $casino.__game "
                    "WHERE tablemoniker = :m AND status = 'settled'",
                    m=self.table_moniker,
                )
            )
            game_row = cur.fetchone()
            self.assertEqual(
                int(game_row["n"]),
                NUM_HANDS,
                f"expected {NUM_HANDS} settled games for {self.table_moniker}, "
                f"got {game_row['n']}",
            )

            cur.execute(
                database.query(
                    "SELECT COUNT(*) AS n FROM $casino.__betlog "
                    "WHERE cardtablemoniker = :m",
                    m=self.table_moniker,
                )
            )
            bet_row = cur.fetchone()
            self.assertEqual(
                int(bet_row["n"]),
                NUM_HANDS * 2,
                f"expected {NUM_HANDS * 2} betlog rows (A+B per hand) "
                f"for {self.table_moniker}, got {bet_row['n']}",
            )


if __name__ == "__main__":
    unittest.main()
