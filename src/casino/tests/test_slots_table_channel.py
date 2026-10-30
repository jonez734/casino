"""A slots table has a table channel, and a spectator sees the spins.

End to end, over real websockets against a real router and server:

  - a player creates a slots table, which creates the table's events and chat channels;
  - a second player watches the table as a spectator, which subscribes them to the channels;
  - the player spins, and the spectator receives the slot result on the events channel.

Slots is single-seat, so the spectator is the only other party. The test fails if a spin is not
broadcast to the table.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import sys
import uuid
from typing import Optional
from unittest.mock import patch

import pytest

sys.path.insert(0, "/home/opencode/data/work/casino/src")

from casino import lib  # noqa: E402
from casino.api.handler import MessageRouter  # noqa: E402
from casino.tests import _dbname  # noqa: E402
from casino.tests._ensure_test_member import grant_test_role  # noqa: E402

multi = importlib.import_module("casino.tests.test_blackjack_multi_user_join")
WebSocketTestClient = multi.WebSocketTestClient
TEST_PASSWORD = multi.TEST_PASSWORD

TEST_PORT = 8771
TEST_URI = f"ws://127.0.0.1:{TEST_PORT}/"

pytestmark = pytest.mark.integration


class TestSlotsTableChannel(__import__("unittest").IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        from bbsengine6 import database
        from bbsengine6.console import member as con_member
        from bbsengine6.net import WebSocketServer

        with contextlib.suppress(Exception):
            await database.reset_async_pool_cache()

        self.args = lib.buildargs().parse_args(_dbname.dbname_args())
        self.pool = database.getpool(self.args)

        suffix = uuid.uuid4().hex[:8]
        self.player = f"slotplayer_{suffix}"
        self.spectator = f"slotwatch_{suffix}"
        self.table_moniker = f"slots_tbl_{suffix}"

        with database.connect(self.args, pool=self.pool) as conn, database.cursor(conn) as cur:
            cur.execute(
                "INSERT INTO bank.__account (moniker, balance, maxtransfer, overdraft_limit) "
                "VALUES ('casino:house', 0, 1000000, 100000) ON CONFLICT (moniker) DO NOTHING"
            )

        for moniker in (self.player, self.spectator):
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
                self.assertTrue(con_member.add(self.args, pool=self.pool))
                grant_test_role(self.args, moniker, pool=self.pool)

        self.server = WebSocketServer(host="127.0.0.1", port=TEST_PORT)
        self.router = MessageRouter(self.args)
        self.router.register_all(self.server)
        for svc in (self.router.table_service, self.router.slot_service):
            svc.allow_legacy_session_only = True
        await self.server.start()
        self._server_started = True

        self.client_player: Optional[WebSocketTestClient] = None
        self.client_spectator: Optional[WebSocketTestClient] = None

    async def asyncTearDown(self) -> None:
        from bbsengine6 import database

        for client in (self.client_player, self.client_spectator):
            if client:
                await client.close()
        if getattr(self, "_server_started", False):
            with contextlib.suppress(Exception):
                await self.server.stop()
        if getattr(self, "pool", None) is not None:
            with database.connect(self.args, pool=self.pool) as conn, database.cursor(conn) as cur:
                cur.execute("DELETE FROM casino.__slot_spin WHERE table_moniker = %s", (self.table_moniker,))
                cur.execute("DELETE FROM casino.__table WHERE moniker = %s", (self.table_moniker,))
                cur.execute(
                    "DELETE FROM engine.__channel WHERE name IN (%s, %s)",
                    (f"casino:table:{self.table_moniker}:events", f"casino:table:{self.table_moniker}:chat"),
                )

    async def _login(self, moniker: str) -> WebSocketTestClient:
        client = WebSocketTestClient(TEST_URI)
        await client.connect()
        await client.send({"type": "auth", "moniker": moniker, "password": TEST_PASSWORD})
        reply = await client.receive()
        self.assertEqual(reply["type"], "auth_result", f"auth for {moniker}: {reply}")
        self.assertTrue(reply["success"], f"auth for {moniker} failed: {reply}")
        return client

    async def test_spectator_receives_a_slot_spin_on_the_table_channel(self) -> None:
        self.client_player = await self._login(self.player)
        self.client_spectator = await self._login(self.spectator)

        await self.client_player.send({
            "type": "create_table",
            "game_type": "slots",
            "min_bet": 1,
            "max_bet": 100,
            "moniker": self.table_moniker,
        })
        created = await self.client_player.receive()
        self.assertEqual(created["type"], "table_created", f"create_table reply: {created}")

        await self.client_player.send({"type": "join_table", "moniker": self.table_moniker})
        joined = await self.client_player.receive()
        self.assertEqual(joined["type"], "joined_table", f"player join reply: {joined}")

        await self.client_spectator.send({"type": "watch_table", "moniker": self.table_moniker})
        watching = await self.client_spectator.receive()
        self.assertEqual(watching["type"], "watching_table", f"watch reply: {watching}")

        await self.client_player.send({"type": "slot_spin", "bet": 1, "table_moniker": self.table_moniker})
        spin_reply = await self.client_player.receive()
        self.assertEqual(spin_reply["type"], "slot_result", f"spin reply: {spin_reply}")

        seen = None
        for _ in range(10):
            try:
                msg = await asyncio.wait_for(self.client_spectator._message_queue.get(), 3)
            except asyncio.TimeoutError:
                break
            if msg.get("type") == "slot_result" and msg.get("table_moniker") == self.table_moniker:
                seen = msg
                break
        self.assertIsNotNone(seen, "the spectator did not receive the spin on the table channel")
        self.assertEqual(seen["player_moniker"], self.player)
        self.assertEqual(seen["spin"]["id"], spin_reply["spin"]["id"])
