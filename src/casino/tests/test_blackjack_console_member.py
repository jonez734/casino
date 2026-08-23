#!/usr/bin/env python3
# casino/tests/test_blackjack_console_member.py
# Integration test: create a member via bbsengine6.console with password
# "12345", authenticate to casino, create a blackjack table, join it,
# and play 3 complete hands end-to-end over the wire.
#
# Member creation exercises bbsengine6.console.member.add() with the
# interactive prompts mocked out: we patch
#   - bbsengine6.console.member._edit   (skips per-field prompts)
#   - bbsengine6.io.inputboolean        (auto-confirms the "add member?" gate)
# so the real insert / setpassword / bank-grant / pgrole code paths run.
#
# Each test run uses a UUID-suffixed moniker (bjconsole-XXXXXXXX) so
# concurrent runs don't collide. asyncTearDown hard-deletes the test
# member + bank account + casino tables/games/betlogs.

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
class TestBlackjackConsoleMember(unittest.IsolatedAsyncioTestCase):
    """Create a member via bbsengine6.console with password '12345',
    authenticate over WS, create a blackjack table, join it, play 3 hands."""

    async def asyncSetUp(self) -> None:
        from bbsengine6 import database
        from bbsengine6.net import WebSocketServer
        from bbsengine6.console import member as con_member

        with contextlib.suppress(Exception):
            await database.reset_async_pool_cache()

        parser = lib.buildargs()
        self.args = parser.parse_args(_dbname.dbname_args())
        self.pool = database.getpool(self.args)

        self.moniker = f"bjconsole_{uuid.uuid4().hex[:8]}"
        self.table_moniker = f"bjconsole_tbl_{uuid.uuid4().hex[:8]}"

        with database.connect(self.args, pool=self.pool) as conn, database.cursor(conn) as cur:
            cur.execute(
                """
                INSERT INTO bank.__account (moniker, balance, maxtransfer, overdraft_limit)
                VALUES ('casino:house', 0, 1000000, 100000)
                ON CONFLICT (moniker) DO NOTHING
                """
            )

        with patch.object(con_member, "_edit") as mock_edit, \
             patch("bbsengine6.io.inputboolean", return_value=True):
            mock_edit.return_value = {
                "moniker": self.moniker,
                "loginid": self.moniker,
                "email": f"{self.moniker}@test.local",
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
            self.assertTrue(ok, f"bbsengine6.console.member.add returned False for {self.moniker}")

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
            with contextlib.suppress(Exception):
                await self.server.stop()

        if hasattr(self, "pool") and self.pool is not None:
            with database.connect(self.args, pool=self.pool) as conn:
                with database.cursor(conn) as cur:
                    cur.execute(
                        "DELETE FROM casino.__betlog WHERE cardtablemoniker LIKE %s",
                        (f"{self.table_moniker}%",),
                    )
                    cur.execute(
                        "DELETE FROM casino.__hand "
                        "WHERE gameid IN ("
                        "SELECT id FROM casino.__game WHERE tablemoniker LIKE %s"
                        ")",
                        (f"{self.table_moniker}%",),
                    )
                    cur.execute(
                        "DELETE FROM casino.__game WHERE tablemoniker LIKE %s",
                        (f"{self.table_moniker}%",),
                    )
                    cur.execute(
                        "DELETE FROM casino.map_cardtable_player "
                        "WHERE cardtablemoniker LIKE %s",
                        (f"{self.table_moniker}%",),
                    )
                    cur.execute(
                        "DELETE FROM casino.__table WHERE moniker LIKE %s",
                        (f"{self.table_moniker}%",),
                    )
                    cur.execute(
                        "DELETE FROM casino.__bank_table WHERE table_moniker LIKE %s",
                        (f"{self.table_moniker}%",),
                    )
                    cur.execute(
                        "DELETE FROM casino.__bank_player WHERE player_moniker = %s",
                        (self.moniker,),
                    )
                    cur.execute(
                        "DELETE FROM casino.__player WHERE moniker = %s",
                        (self.moniker,),
                    )
                    cur.execute(
                        "DELETE FROM bank.__account WHERE moniker = %s",
                        (self.moniker,),
                    )
                    cur.execute(
                        "DELETE FROM engine.__member WHERE moniker = %s",
                        (self.moniker,),
                    )
                conn.commit()

            self.pool.close()
            self.pool = None

    async def _wait_for_game_state(self, max_messages: int = 10) -> dict:
        messages = await self.client.receive_messages(max_count=max_messages, timeout=5.0)
        for msg in messages:
            if msg.get("type") == "game_state":
                return msg
        self.fail(f"No game_state received after {max_messages} messages: {messages}")

    async def _play_one_hand(self, bet_amount: int) -> dict:
        await self.client.send({"type": "bet", "amount": bet_amount})
        dealing = await self._wait_for_game_state()
        self.assertEqual(
            len(dealing.get("player_hand", [])),
            2,
            f"expected 2 cards after bet, got {dealing.get('player_hand')}",
        )
        self.assertGreater(
            dealing.get("player_total", 0),
            0,
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

    async def test_console_member_create_then_play_three_hands(self) -> None:
        """End-to-end: create member via console, auth, create_table,
        join_table, 3 bet+stand cycles, verify DB state."""
        from bbsengine6 import database

        self.client = WebSocketTestClient(TEST_URI)
        await self.client.connect()
        self.assertTrue(self.client._running, "Failed to connect")

        await self.client.send(
            {"type": "auth", "moniker": self.moniker, "password": TEST_PASSWORD}
        )
        auth = await self.client.receive()
        self.assertEqual(auth["type"], "auth_result", f"auth reply: {auth}")
        self.assertTrue(auth["success"], f"auth success=False: {auth}")
        self.assertEqual(auth["moniker"], self.moniker)
        starting_balance = int(auth["balance"])
        self.assertGreater(starting_balance, 0, "test player should have balance > 0")

        await self.client.send(
            {
                "type": "create_table",
                "game_type": "blackjack",
                "min_bet": 10,
                "max_bet": 1000,
                "moniker": self.table_moniker,
            }
        )
        created = await self.client.receive()
        self.assertEqual(created["type"], "table_created", f"create_table reply: {created}")
        self.assertEqual(created["moniker"], self.table_moniker)

        await self.client.send({"type": "join_table", "moniker": self.table_moniker})
        joined = await self.client.receive()
        self.assertEqual(joined["type"], "joined_table", f"join_table reply: {joined}")
        self.assertEqual(joined["moniker"], self.table_moniker)

        bet_amount = 10
        for _ in range(3):
            settled = await self._play_one_hand(bet_amount)
            self.assertEqual(
                settled.get("table_moniker"),
                self.table_moniker,
                "game_state should reference the joined table",
            )

        with database.connect(self.args, pool=self.pool) as conn, database.cursor(conn) as cur:
            cur.execute(
                database.query(
                    "SELECT COUNT(*) AS n FROM $casino.__game "
                    "WHERE tablemoniker = :m AND status = 'settled'",
                    m=self.table_moniker,
                )
            )
            row = cur.fetchone()
            self.assertEqual(
                int(row["n"]),
                3,
                f"expected 3 settled games for {self.table_moniker}, got {row['n']}",
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
                3,
                f"expected 3 betlog rows for {self.table_moniker}, got {bet_row['n']}",
            )

            cur.execute(
                database.query(
                    "SELECT COUNT(*) AS n FROM $engine.__member WHERE moniker = :m",
                    m=self.moniker,
                )
            )
            member_row = cur.fetchone()
            self.assertEqual(
                int(member_row["n"]),
                1,
                f"test member {self.moniker} should exist in engine.__member",
            )

            cur.execute(
                database.query(
                    "SELECT COUNT(*) AS n FROM $bank.__account WHERE moniker = :m",
                    m=self.moniker,
                )
            )
            bank_row = cur.fetchone()
            self.assertEqual(
                int(bank_row["n"]),
                1,
                f"test member {self.moniker} should have a bank.__account row",
            )


if __name__ == "__main__":
    unittest.main()
