"""table_info: a moniker's game type and owner, before the player joins it.

The client looks a table up before ``join_table`` so the game-action commands can
show or hide for the table's game type. In-memory poker tables are checked first,
then the database. A missing table is ``found: false``, not an error.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch


class TestTableInfo(unittest.IsolatedAsyncioTestCase):
    def _handler(self, poker_tables=None):
        from casino.api.handler import TableServiceHandler

        handler = TableServiceHandler.__new__(TableServiceHandler)
        handler.args = MagicMock()
        if poker_tables is None:
            handler.poker_service_handler = None
        else:
            handler.poker_service_handler = MagicMock()
            handler.poker_service_handler.list_tables = MagicMock(return_value=poker_tables)
        return handler

    async def test_database_table_returns_game_type_and_owner(self):
        handler = self._handler()
        row = {"moniker": "bj1", "type": "blackjack", "ownermoniker": "jam"}
        with patch("casino.api.handler.async_dal_table.get_table", AsyncMock(return_value=row)), \
             patch("casino.api.handler._resolve_async_pool", AsyncMock(return_value=None)):
            reply = await handler._handle_table_info(MagicMock(), {"moniker": "bj1"})
        self.assertEqual(reply, {
            "type": "table_info", "found": True, "moniker": "bj1",
            "game_type": "blackjack", "owner": "jam",
        })

    async def test_poker_table_is_checked_before_the_database(self):
        handler = self._handler(poker_tables=[
            {"moniker": "pk1", "type": "poker", "variant": "holdem"},
        ])
        get_table = AsyncMock()
        with patch("casino.api.handler.async_dal_table.get_table", get_table):
            reply = await handler._handle_table_info(MagicMock(), {"moniker": "pk1"})
        get_table.assert_not_awaited()
        self.assertTrue(reply["found"])
        self.assertEqual(reply["game_type"], "poker")

    async def test_missing_table_is_found_false_not_an_error(self):
        handler = self._handler(poker_tables=[])
        with patch("casino.api.handler.async_dal_table.get_table", AsyncMock(return_value=None)), \
             patch("casino.api.handler._resolve_async_pool", AsyncMock(return_value=None)):
            reply = await handler._handle_table_info(MagicMock(), {"moniker": "nope"})
        self.assertEqual(reply, {"type": "table_info", "found": False, "moniker": "nope"})

    async def test_missing_moniker_is_an_invalid_request(self):
        handler = self._handler()
        reply = await handler._handle_table_info(MagicMock(), {})
        self.assertEqual(reply["type"], "error")
        self.assertEqual(reply["code"], "invalid_request")

    async def test_dispatch_routes_table_info(self):
        handler = self._handler()
        handler._handle_table_info = AsyncMock(return_value={"type": "table_info"})
        reply = await handler.handle_message(None, MagicMock(), "/", {"type": "table_info", "moniker": "x"})
        handler._handle_table_info.assert_awaited_once()
        self.assertEqual(reply, {"type": "table_info"})


if __name__ == "__main__":
    unittest.main()
