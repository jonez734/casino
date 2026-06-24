#!/usr/bin/env python3
# casino/tests/test_bed.py
# Integration tests for BED (BBS Engine Daemon)

import argparse
import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import websockets

import sys
sys.path.insert(0, "/home/opencode/data/work/casino/src")


class TestBEDMocked(unittest.IsolatedAsyncioTestCase):
    """Test BED with mocked database."""

    async def asyncSetUp(self):
        """Start BED before each test."""
        from bbsengine6.net import WebSocketServer
        from casino.api.handler import MessageRouter
        from casino.bed import BED

        self.mock_args = MagicMock()
        self.mock_args.databasename = "test"
        self.mock_args.databasehost = "localhost"
        self.mock_args.databaseport = 5432
        self.mock_args.databaseuser = "test"
        self.mock_args.databasepassword = "test"
        self.mock_args.debug = False
        self.mock_args.host = "127.0.0.1"
        self.mock_args.port = 18771

        mock_pool = MagicMock()
        mock_pool.connection.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_pool.connection.return_value.__exit__ = MagicMock(return_value=False)
        self.mock_args.pool = mock_pool

        self.bed = BED(self.mock_args)

        self.bed.server = WebSocketServer(
            host=self.mock_args.host,
            port=self.mock_args.port,
        )

        self.bed.router = MessageRouter(self.mock_args)
        self.bed.router.register_all(self.bed.server)

        await self.bed.server.start()
        self._server_started = True

    async def asyncTearDown(self):
        """Stop BED after each test."""
        if hasattr(self, "_server_started") and self._server_started:
            await self.bed.server.stop()

    async def test_bed_starts(self):
        """Test BED starts successfully."""
        self.assertTrue(self.bed.server is not None)
        self.assertTrue(self.bed.server.is_running)

    async def test_connect_to_bed(self):
        """Test connecting to BED server."""
        uri = f"ws://{self.mock_args.host}:{self.mock_args.port}/"

        async with websockets.connect(uri) as ws:
            self.assertTrue(ws.state == websockets.State.OPEN)

    async def test_ping_pong(self):
        """Test ping/pong."""
        uri = f"ws://{self.mock_args.host}:{self.mock_args.port}/"

        async with websockets.connect(uri) as ws:
            await ws.send(json.dumps({"type": "ping"}))
            response = json.loads(await ws.recv())

            self.assertEqual(response["type"], "pong")
            self.assertIn("timestamp", response)

    async def test_list_services(self):
        """Test listing registered services."""
        services = self.bed.server.list_services()
        self.assertIsInstance(services, dict)


class TestBEDParseArgs(unittest.IsolatedAsyncioTestCase):
    """Test BED argument parsing."""

    def test_default_port(self):
        """Test default port is 8765."""
        with patch("sys.argv", ["bed"]):
            from casino.bed import parse_args
            args = parse_args()
            self.assertEqual(args.port, 8765)

    def test_default_host(self):
        """Test default host is 0.0.0.0."""
        with patch("sys.argv", ["bed"]):
            from casino.bed import parse_args
            args = parse_args()
            self.assertEqual(args.host, "0.0.0.0")

    def test_custom_port(self):
        """Test custom port can be specified."""
        with patch("sys.argv", ["bed", "--port", "9999"]):
            from casino.bed import parse_args
            args = parse_args()
            self.assertEqual(args.port, 9999)

    def test_custom_host(self):
        """Test custom host can be specified."""
        with patch("sys.argv", ["bed", "--host", "localhost"]):
            from casino.bed import parse_args
            args = parse_args()
            self.assertEqual(args.host, "localhost")


if __name__ == "__main__":
    unittest.main()
