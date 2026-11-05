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
import unittest
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
from casino.tests._ws_replies import receive_join_reply  # noqa: E402

multi = importlib.import_module("casino.tests.test_blackjack_multi_user_join")
WebSocketTestClient = multi.WebSocketTestClient
TEST_PASSWORD = multi.TEST_PASSWORD

TEST_PORT = 8771
TEST_URI = f"ws://127.0.0.1:{TEST_PORT}/"

pytestmark = pytest.mark.integration


class TestSlotsTableChannel(__import__("unittest").IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._issued_tokens: list[str] = []
        self._tokens: dict[str, str] = {}
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
        # Wire the router the way bed does in production: the token gate needs the secret, the
        # database token store (the rows _issue_token writes), and an instance id. Without them
        # the gate is a no-op and a spin is refused as having no session token.
        from bed.api.token_store import DBTokenStore

        self._test_secret = b"slots-table-channel-test-secret-32b!!"
        self.router = MessageRouter(
            self.args,
            secret=self._test_secret,
            token_store=DBTokenStore(self.args),
            instance_id="casino-test",
        )
        self.router.register_all(self.server)
        for svc in (self.router.table_service, self.router.slot_service):
            svc.allow_legacy_session_only = True
        await self.server.start()
        self._server_started = True

        self.client_player: Optional[WebSocketTestClient] = None
        self.client_spectator: Optional[WebSocketTestClient] = None

    async def asyncTearDown(self) -> None:
        from bbsengine6 import database

        # Remove the bearer tokens this test minted, so reruns leave no rows in engine.__bed_token.
        if getattr(self, "_issued_tokens", None):
            from bed.api.token_store import DBTokenStore

            store = DBTokenStore(self.args)
            for token in self._issued_tokens:
                store.delete(token)

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

    def _issue_token(self, moniker: str) -> str:
        """Mint a signed bed bearer token for ``moniker``, the way bed does at login.

        The claims are built as bed's AuthService._mint_record builds them, signed with the router's
        secret (the same secret the token gate verifies with), and the row is written to
        engine.__bed_token through DBTokenStore. Nothing is bypassed: the server verifies the
        signature, the expiry, and the stored row, and the spin settles through the real database.
        """
        import time
        import uuid

        from bed.api.token_store import DBTokenStore, TokenRecord
        from casino.api._auth import _TOKEN_CLAIM_VERSION as TOKEN_CLAIM_VERSION, encode_token

        now = time.time()
        session_id = f"sess-{moniker}-{uuid.uuid4().hex[:8]}"
        websocket_id = f"ws-{moniker}-{uuid.uuid4().hex[:8]}"
        claims = {
            "version": TOKEN_CLAIM_VERSION,
            "moniker": moniker,
            "issued_at": now,
            "expires_at": now + 3600,
            "session_id": session_id,
            "is_sysop": False,
            "bed_instance_id": "casino-test",
            "websocket_id": websocket_id,
            "loginid": moniker,
        }
        token = encode_token(claims, self._test_secret)
        DBTokenStore(self.args).put(TokenRecord(
            token=token, moniker=moniker, session_id=session_id, issued_at=now,
            expires_at=now + 3600, is_sysop=False, bed_instance_id="casino-test",
            websocket_id=websocket_id, claims=claims, loginid=moniker,
        ))
        self._issued_tokens.append(token)
        self._tokens[moniker] = token
        return token

    async def _login(self, moniker: str) -> WebSocketTestClient:
        client = WebSocketTestClient(TEST_URI)
        await client.connect()
        await client.send({
            "type": "auth", "moniker": moniker, "password": TEST_PASSWORD,
            "token": self._issue_token(moniker),
        })
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
        joined = await receive_join_reply(self.client_player)
        self.assertEqual(joined["type"], "joined_table", f"player join reply: {joined}")

        await self.client_spectator.send({"type": "watch_table", "moniker": self.table_moniker})
        watching = await self.client_spectator.receive()
        self.assertEqual(watching["type"], "watching_table", f"watch reply: {watching}")

        await self.client_player.send({
            "type": "slot_spin", "bet": 1, "table_moniker": self.table_moniker,
            "token": self._tokens[self.player],
        })
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


class TestSlotsBigWinShout(TestSlotsTableChannel):
    """A big win reaches a connected player who is not at the table, over real websockets."""

    async def test_a_big_win_is_shouted_to_a_player_who_is_not_at_the_table(self) -> None:
        from casino.slots.lib import BIG_WIN_MULTIPLIER
        # The spectator stays in the lobby: they never join or watch the table.

        self.client_player = await self._login(self.player)
        self.client_spectator = await self._login(self.spectator)

        await self.client_player.send({
            "type": "create_table", "game_type": "slots",
            "min_bet": 1, "max_bet": 100, "moniker": self.table_moniker,
        })
        self.assertEqual((await self.client_player.receive())["type"], "table_created")
        await self.client_player.send({"type": "join_table", "moniker": self.table_moniker})
        self.assertEqual((await receive_join_reply(self.client_player))["type"], "joined_table")

        forced = {"success": True, "spin": {
            "id": 99, "bet": 1, "payout": 1 * BIG_WIN_MULTIPLIER, "net": BIG_WIN_MULTIPLIER - 1,
            "reels": [], "center_row": [], "wins": [],
        }}
        from unittest.mock import patch as _patch

        with _patch.object(self.router.slot_service, "_handle_spin", return_value=forced):
            await self.client_player.send({
                "type": "slot_spin", "bet": 1, "table_moniker": self.table_moniker,
                "token": self._tokens[self.player],
            })
            # The player is subscribed to casino:global too, so the shout may arrive first. Take
            # the spin reply by type.
            reply = None
            for _ in range(5):
                msg = await self.client_player.receive()
                if msg.get("type") == "slot_result":
                    reply = msg
                    break
        self.assertIsNotNone(reply, "the player did not receive the spin reply")
        self.assertEqual(reply["type"], "slot_result")

        shout = None
        for _ in range(10):
            try:
                msg = await asyncio.wait_for(self.client_spectator._message_queue.get(), 3)
            except asyncio.TimeoutError:
                break
            if msg.get("type") == "big_win":
                shout = msg
                break
        self.assertIsNotNone(shout, "the lobby player did not receive the big-win shout")
        self.assertEqual(shout["player_moniker"], self.player)
        self.assertEqual(shout["multiplier"], BIG_WIN_MULTIPLIER)
