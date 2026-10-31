"""Table creation pushes owns_tables to the creator's socket.

The client's ``table update`` gate depends on ``owns_tables``. Creating a table makes
the creator an owner, so the server sends ``{"type": "owns_tables", "owns_tables": true}``
on that socket. A failed send is logged and does not fail the create.
"""

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


class TestCreateTableOwnsTablesPush(unittest.IsolatedAsyncioTestCase):
    def _handler(self, create_result):
        from casino.api.handler import TableServiceHandler

        handler = TableServiceHandler.__new__(TableServiceHandler)
        handler.args = MagicMock()
        handler.table_service = MagicMock()
        handler.table_service.create_table = MagicMock(return_value=create_result)
        state = MagicMock(moniker="jam", is_sysop=False)
        handler._check_access = MagicMock(return_value=(state, None))
        return handler

    async def test_successful_create_pushes_owns_tables_true_to_creator(self):
        handler = self._handler({
            "success": True,
            "table": {"moniker": "t1", "location": "x", "hidden": False},
            "message": "Table t1 created",
        })
        ws = MagicMock()
        ws.send = AsyncMock()
        with patch("casino.services.table_channels.create_table_channels"):
            reply = await handler._handle_create_table(ws, {"type": "casino_create_table"})
            # The push is a task scheduled after the handler returns; let it run, as the
            # server loop does before it sends the next message.
            await asyncio.sleep(0)

        ws.send.assert_awaited_once()
        sent = json.loads(ws.send.await_args.args[0])
        self.assertEqual(sent, {"type": "owns_tables", "owns_tables": True})
        self.assertEqual(reply["type"], "table_created")

    async def test_failed_push_does_not_fail_the_create(self):
        handler = self._handler({
            "success": True,
            "table": {"moniker": "t1", "location": "x", "hidden": False},
            "message": "Table t1 created",
        })
        ws = MagicMock()
        ws.send = AsyncMock(side_effect=RuntimeError("socket closed"))
        with patch("casino.services.table_channels.create_table_channels"):
            reply = await handler._handle_create_table(ws, {"type": "casino_create_table"})

        self.assertEqual(reply["type"], "table_created")
        self.assertEqual(reply["moniker"], "t1")

    async def test_refused_create_pushes_nothing(self):
        handler = self._handler({"success": False, "message": "name taken"})
        ws = MagicMock()
        ws.send = AsyncMock()
        await handler._handle_create_table(ws, {"type": "casino_create_table"})
        ws.send.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
