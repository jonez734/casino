"""The client stores is_sysop and owns_tables from the login reply and the push.

The menu gates ``table update`` and the sysop commands on these fields. They come
from ``auth_result`` / ``reconnect_result`` at login, and ``owns_tables`` is updated
by the server's push when the player creates a table.
"""

import argparse
import asyncio
import unittest
from unittest.mock import patch


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _client():
    from casino.client import CasinoClient

    return CasinoClient(argparse.Namespace(bed_host="127.0.0.1", bed_port=8765, bed_path="/"))


class TestClientOwnsTablesState(unittest.TestCase):
    def test_auth_result_stores_is_sysop_and_owns_tables(self):
        client = _client()
        with patch("casino.client.casino_client.io.echo"):
            _run(client.handle_message({
                "type": "auth_result", "success": True, "moniker": "jam",
                "balance": 1, "is_sysop": True, "owns_tables": True,
            }))
        self.assertIs(client.is_sysop, True)
        self.assertIs(client.owns_tables, True)

    def test_reconnect_result_stores_is_sysop_and_owns_tables(self):
        client = _client()
        with patch("casino.client.casino_client.io.echo"):
            _run(client.handle_message({
                "type": "reconnect_result", "success": True, "moniker": "alice",
                "balance": 2, "is_sysop": False, "owns_tables": False,
            }))
        self.assertIs(client.is_sysop, False)
        self.assertIs(client.owns_tables, False)

    def test_missing_fields_default_to_false(self):
        client = _client()
        with patch("casino.client.casino_client.io.echo"):
            _run(client.handle_message({
                "type": "auth_result", "success": True, "moniker": "x", "balance": 0,
            }))
        self.assertIs(client.is_sysop, False)
        self.assertIs(client.owns_tables, False)

    def test_owns_tables_push_updates_the_flag(self):
        client = _client()
        client.owns_tables = False
        with patch("casino.client.casino_client.io.echo"):
            _run(client.handle_message({"type": "owns_tables", "owns_tables": True}))
        self.assertIs(client.owns_tables, True)
        with patch("casino.client.casino_client.io.echo"):
            _run(client.handle_message({"type": "owns_tables", "owns_tables": False}))
        self.assertIs(client.owns_tables, False)


if __name__ == "__main__":
    unittest.main()
