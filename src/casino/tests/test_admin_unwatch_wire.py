"""``admin unwatch`` sends ``stop_watching``, the message type the server handles.

The server dispatches ``stop_watching`` (api/handler.py). Sending any other type
is refused as unknown, so the unwatch command would silently do nothing.
"""

import asyncio
import unittest
from unittest.mock import MagicMock, patch

from casino.commands.admin import lib as admin_lib


class TestAdminUnwatchWire(unittest.TestCase):
    def test_unwatch_sends_stop_watching(self):
        sent = []

        async def send(msg):
            sent.append(msg)

        loop = asyncio.new_event_loop()
        try:
            client = MagicMock()
            client._loop = loop
            client.send = send
            args = MagicMock()
            with patch("casino.commands.admin.lib.io.inputstring", return_value="t1"), \
                 patch("casino.commands.admin.lib.io.echo"):
                admin_lib.unwatch_table(args, client=client)
        finally:
            loop.close()
        self.assertTrue(sent, "unwatch_table sent nothing")
        self.assertEqual(sent[0]["type"], "stop_watching")
        self.assertEqual(sent[0]["moniker"], "t1")


if __name__ == "__main__":
    unittest.main()
