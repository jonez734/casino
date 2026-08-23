#!/usr/bin/env python3
# casino/tests/test_blackjack_multi_user_join.py
# Integration test: user A creates a blackjack table, then user B
# (a second freshly-created member via bbsengine6.console.member.add)
# joins A's table over the wire. Verifies:
#   1. both members authenticate successfully,
#   2. A's create_table + join_table succeed,
#   3. B's join_table succeeds against A's existing table,
#   4. both players are recorded as seated in
#      casino.map_cardtable_player,
#   5. when A bets, B (a 2nd subscriber on the same table channel)
#      receives the resulting game_state over its websocket -- this
#      pins the fix to bbsengine6.net.transport.channel_publish that
#      routes via session-id fan-out instead of the broken
#      path-based broadcast.
#
# Each test run uses a UUID-suffixed moniker triple so concurrent
# runs don't collide. asyncTearDown hard-deletes all test rows.
#
# Note: blackjack does NOT enforce the single-seater invariant that
# slots does (see api/handler.py:_handle_join_table), so a second
# player can join a blackjack table.

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
TEST_PORT = 8768
TEST_URI = f"ws://127.0.0.1:{TEST_PORT}/"
TEST_PASSWORD = "12345"


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
class TestBlackjackMultiUserJoin(unittest.IsolatedAsyncioTestCase):
    """User A creates a blackjack table; user B joins it."""

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
        self.moniker_a = f"bjconsole_a_{suffix}"
        self.moniker_b = f"bjconsole_b_{suffix}"
        self.table_moniker = f"bjconsole_tbl_{suffix}"

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

    async def test_second_user_can_join_existing_table(self) -> None:
        """End-to-end: A creates a blackjack table, B joins it, both
        are seated in casino.map_cardtable_player, and B receives the
        game_state broadcast when A bets (regression for the channel
        publish fix in bbsengine6.net.transport.channel_publish)."""
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
        self.assertEqual(auth_a["moniker"], self.moniker_a)

        await self.client_b.send(
            {"type": "auth", "moniker": self.moniker_b, "password": TEST_PASSWORD}
        )
        auth_b = await self.client_b.receive()
        self.assertEqual(auth_b["type"], "auth_result", f"B auth reply: {auth_b}")
        self.assertTrue(auth_b["success"], f"B auth success=False: {auth_b}")
        self.assertEqual(auth_b["moniker"], self.moniker_b)

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
        self.assertEqual(created["moniker"], self.table_moniker)

        await self.client_a.send({"type": "join_table", "moniker": self.table_moniker})
        joined_a = await self.client_a.receive()
        self.assertEqual(joined_a["type"], "joined_table", f"A join reply: {joined_a}")
        self.assertEqual(joined_a["moniker"], self.table_moniker)

        await self.client_b.send({"type": "join_table", "moniker": self.table_moniker})
        joined_b = await self.client_b.receive()
        self.assertEqual(joined_b["type"], "joined_table", f"B join reply: {joined_b}")
        self.assertEqual(joined_b["moniker"], self.table_moniker)

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

        await self.client_a.send({"type": "bet", "amount": 10})
        game_a = await self._wait_for_game_state(self.client_a)
        self.assertEqual(game_a.get("table_moniker"), self.table_moniker)
        self.assertEqual(
            len(game_a.get("player_hand", [])),
            2,
            f"expected 2 cards after A's bet, got {game_a.get('player_hand')}",
        )

        game_b = await self._wait_for_game_state(self.client_b)
        self.assertEqual(game_b.get("table_moniker"), self.table_moniker)
        self.assertEqual(
            game_b.get("phase"),
            game_a.get("phase"),
            f"B should see same game_state as A, got A={game_a} B={game_b}",
        )

    async def _wait_for_game_state(
        self, client: WebSocketTestClient, max_messages: int = 10
    ) -> dict:
        messages = await client.receive_messages(max_count=max_messages, timeout=5.0)
        for msg in messages:
            if msg.get("type") == "game_state":
                return msg
        self.fail(f"No game_state received after {max_messages} messages: {messages}")


if __name__ == "__main__":
    unittest.main()
