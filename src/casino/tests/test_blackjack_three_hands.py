#!/usr/bin/env python3
# casino/tests/test_blackjack_three_hands.py
# Integration test: authenticate to casino, create a blackjack table, join it,
# and play 3 complete hands end-to-end over the wire.

import asyncio
import json
import sys
import unittest
from typing import Optional

import pytest

sys.path.insert(0, "/home/opencode/data/work/casino/src")

import contextlib

import websockets
from websockets.exceptions import ConnectionClosed

from casino import lib
from casino.api.handler import MessageRouter

DEFAULT_TIMEOUT = 10.0
PING_INTERVAL = 30.0
TEST_PORT = 8767
TEST_URI = f"ws://127.0.0.1:{TEST_PORT}/"
TEST_TABLE_PREFIX = "blackjack-3h-"


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
class TestBlackjackThreeHands(unittest.IsolatedAsyncioTestCase):
    """Authenticate, create a blackjack table, join it, and play 3 complete hands."""

    async def asyncSetUp(self) -> None:
        from bbsengine6 import database
        from bbsengine6.net import WebSocketServer

        with contextlib.suppress(Exception):
            await database.reset_async_pool_cache()

        parser = lib.buildargs()
        self.args = parser.parse_args(["--databasename", "zoid6"])
        self.pool = database.getpool(self.args)

        with database.connect(self.args, pool=self.pool) as conn, database.cursor(conn) as cur:
            cur.execute(
                "INSERT INTO engine.__member (moniker, loginid, password, email, credits) "
                "VALUES ('jam', 'jam', crypt('test', gen_salt('md5')), 'jam@test.local', 100000) "
                "ON CONFLICT (moniker) DO UPDATE SET "
                "password = crypt('test', gen_salt('md5')), credits = 100000"
            )
            cur.execute(
                "INSERT INTO bank.__account (moniker, balance) VALUES ('jam', 100000) "
                "ON CONFLICT (moniker) DO UPDATE SET balance = 100000"
            )
            cur.execute(
                "INSERT INTO engine.__member (moniker, loginid, password, email, credits) "
                "VALUES ('__dealer__', '__dealer__', crypt('x', gen_salt('md5')), "
                "'dealer@casino.local', 0) "
                "ON CONFLICT (moniker) DO NOTHING"
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
        self.client: Optional[WebSocketTestClient] = None

    async def asyncTearDown(self) -> None:
        from bbsengine6 import database

        if self.client:
            await self.client.close()
        if hasattr(self, "_server_started") and self._server_started:
            await self.server.stop()

        if hasattr(self, "pool") and self.pool is not None:
            try:
                with database.connect(self.args, pool=self.pool) as conn, database.cursor(conn) as cur:
                    cur.execute("UPDATE engine.__member SET credits = 100000 WHERE moniker = 'jam'")
                    cur.execute("UPDATE bank.__account SET balance = 100000 WHERE moniker = 'jam'")
                    for sql in (
                        "DELETE FROM casino.__bank_table WHERE table_moniker LIKE :p",
                        "DELETE FROM casino.__table WHERE moniker LIKE :p",
                        "DELETE FROM casino.__game WHERE tablemoniker LIKE :p",
                        "DELETE FROM casino.map_cardtable_player "
                        "WHERE cardtablemoniker LIKE :p",
                        "DELETE FROM casino.__betlog WHERE cardtablemoniker LIKE :p",
                    ):
                        cur.execute(
                            database.query(sql, p=f"{TEST_TABLE_PREFIX}%")
                        )
            except Exception:
                pass

            self.pool.close()
            self.pool = None

    async def _wait_for_game_state(self, max_messages: int = 10) -> dict:
        """Drain the receive queue until a game_state message arrives."""
        messages = await self.client.receive_messages(max_count=max_messages, timeout=5.0)
        for msg in messages:
            if msg.get("type") == "game_state":
                return msg
        self.fail(f"No game_state received after {max_messages} messages: {messages}")

    async def _play_one_hand(self, table_moniker: str, bet_amount: int) -> dict:
        """Place a bet, stand, and return the post-stand game_state."""
        await self.client.send({"type": "bet", "amount": bet_amount})
        dealing = await self._wait_for_game_state()
        self.assertEqual(
            len(dealing.get("player_hand", [])),
            2,
            f"expected 2 cards after bet, got {dealing.get('player_hand')}",
        )
        self.assertGreater(
            dealing.get("player_total", 0), 0,
            "player_total should be > 0 after bet",
        )

        await self.client.send({"type": "stand"})
        settled = await self._wait_for_game_state()
        self.assertEqual(
            settled.get("phase"),
            "settled",
            f"expected phase=settled after stand, got {settled.get('phase')}",
        )
        return settled

    async def test_auth_create_join_play_three_hands(self) -> None:
        """End-to-end: auth, create_table, join_table, 3 bet+stand cycles."""
        self.client = WebSocketTestClient(TEST_URI)
        await self.client.connect()
        self.assertTrue(self.client._running, "Failed to connect")

        # 1. Authenticate
        await self.client.send({"type": "auth", "moniker": "jam", "password": "test"})
        auth = await self.client.receive()
        self.assertEqual(auth["type"], "auth_result")
        self.assertTrue(auth["success"])
        self.assertEqual(auth["moniker"], "jam")
        starting_balance = int(auth["balance"])
        self.assertGreater(starting_balance, 0, "test player should have balance > 0")

        # 2. Create a blackjack table (use a unique moniker to avoid duplicates)
        table_moniker = f"{TEST_TABLE_PREFIX}jam"
        await self.client.send(
            {
                "type": "create_table",
                "game_type": "blackjack",
                "min_bet": 10,
                "max_bet": 1000,
                "moniker": table_moniker,
            }
        )
        created = await self.client.receive()
        self.assertEqual(created["type"], "table_created")
        self.assertEqual(created["moniker"], table_moniker)

        # 3. Join the table
        await self.client.send({"type": "join_table", "moniker": table_moniker})
        joined = await self.client.receive()
        self.assertEqual(joined["type"], "joined_table")
        self.assertEqual(joined["moniker"], table_moniker)

        # 4. Play 3 hands (bet -> stand)
        bet_amount = 10
        for _ in range(3):
            settled = await self._play_one_hand(table_moniker, bet_amount)
            self.assertEqual(
                settled.get("table_moniker"),
                table_moniker,
                "game_state should reference the joined table",
            )

        # 5. Verify the database state: 3 settled games for this table
        from bbsengine6 import database

        with database.connect(self.args, pool=self.pool) as conn, database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "SELECT COUNT(*) AS n FROM $casino.__game "
                    "WHERE tablemoniker = :m AND status = 'settled'",
                    m=table_moniker,
                )
            )
            row = cur.fetchone()
            self.assertEqual(
                int(row["n"]),
                3,
                f"expected 3 settled games for {table_moniker}, got {row['n']}",
            )

            cur.execute(
                database.query(
                    "SELECT COUNT(*) AS n FROM $casino.__betlog "
                    "WHERE cardtablemoniker = :m",
                    m=table_moniker,
                )
            )
            bet_row = cur.fetchone()
            self.assertEqual(
                int(bet_row["n"]),
                3,
                f"expected 3 betlog rows for {table_moniker}, got {bet_row['n']}",
            )


if __name__ == "__main__":
    unittest.main()
