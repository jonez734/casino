#!/usr/bin/env python3
# casino/tests/test_server.py
# Integration tests for server with mocked database

import argparse
import asyncio
import json
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, "/home/opencode/data/work/casino/src")

import websockets


class TestServerMocked(unittest.IsolatedAsyncioTestCase):
    """Test server with mocked database."""

    async def asyncSetUp(self):
        """Start server before each test."""
        # Import here to avoid issues if dependencies missing
        from bbsengine6.net import WebSocketServer
        from casino.api.handler import MessageRouter

        # Create mock args
        self.mock_args = MagicMock()
        self.mock_args.pool = MagicMock()
        self.mock_args.databasename = "test"

        # Create server
        self.server = WebSocketServer(host="127.0.0.1", port=18770)

        # Create router with mock
        self.router = MessageRouter(self.mock_args)

        # Mock the services
        self.router.auth_service.player_service = MagicMock()
        self.router.auth_service.player_service.authenticate = MagicMock(
            return_value={"success": True, "moniker": "testuser", "balance": 1000}
        )
        self.router.auth_service.player_service.get_balance = MagicMock(
            return_value=1000
        )

        self.router.table_service.table_service = MagicMock()
        self.router.table_service.table_service.list_tables = MagicMock(
            return_value=[
                {
                    "id": 1,
                    "game_type": "blackjack",
                    "min_bet": 10,
                    "max_bet": 100,
                    "owner": "testuser",
                    "players": [],
                    "spectators": [],
                }
            ]
        )

        # Register services
        self.router.register_all(self.server)

        # Start server
        await self.server.start()
        self._server_started = True

    async def asyncTearDown(self):
        """Stop server after each test."""
        if hasattr(self, "_server_started") and self._server_started:
            await self.server.stop()

    async def test_connect_and_auth(self):
        """Test connecting and authenticating."""
        uri = "ws://127.0.0.1:18770/"

        async with websockets.connect(uri) as ws:
            # Send auth
            await ws.send(
                json.dumps(
                    {"type": "auth", "moniker": "testuser", "password": "testpass"}
                )
            )

            # Receive response
            response = json.loads(await ws.recv())

            self.assertEqual(response["type"], "auth_result")
            self.assertTrue(response["success"])
            self.assertEqual(response["moniker"], "testuser")
            self.assertEqual(response["balance"], 1000)

    async def test_list_tables(self):
        """Test listing tables."""
        uri = "ws://127.0.0.1:18770/"

        async with websockets.connect(uri) as ws:
            # List tables (no auth needed)
            await ws.send(json.dumps({"type": "list_tables"}))

            # Receive response
            response = json.loads(await ws.recv())

            self.assertEqual(response["type"], "table_list")
            self.assertEqual(len(response["tables"]), 1)
            self.assertEqual(response["tables"][0]["id"], 1)

    async def test_ping_pong(self):
        """Test ping/pong."""
        uri = "ws://127.0.0.1:18770/"

        async with websockets.connect(uri) as ws:
            # Send ping
            await ws.send(json.dumps({"type": "ping"}))

            # Receive pong
            response = json.loads(await ws.recv())

            self.assertEqual(response["type"], "pong")
            self.assertIn("timestamp", response)

    async def test_invalid_message(self):
        """Test handling invalid message."""
        uri = "ws://127.0.0.1:18770/"

        async with websockets.connect(uri) as ws:
            # Send invalid message
            await ws.send(json.dumps({"type": "invalid_message_type"}))

            # Receive error
            response = json.loads(await ws.recv())

            self.assertEqual(response["type"], "error")
            self.assertEqual(response["code"], "no_handler")


class TestBlackjackGame(unittest.IsolatedAsyncioTestCase):
    """Test blackjack game logic."""

    def test_deck_creation(self):
        """Test deck creation."""
        from casino.services.game import GameService

        args = MagicMock()
        game = GameService(args)

        # Test shoe creation directly
        shoe = game._create_shoe(decks=1)
        self.assertEqual(len(shoe), 52)  # 52 cards in one deck
        self.assertIn("AH", shoe)  # Ace of hearts should be in deck

    def test_card_value(self):
        """Test card values."""
        from casino.services.game import GameService

        args = MagicMock()
        game = GameService(args)

        # Number cards
        self.assertEqual(game._card_value("2H"), 2)
        self.assertEqual(game._card_value("9H"), 9)

        # Face cards
        self.assertEqual(game._card_value("JH"), 10)
        self.assertEqual(game._card_value("QH"), 10)
        self.assertEqual(game._card_value("KH"), 10)

        # Ace
        self.assertEqual(game._card_value("AH"), 11)

    def test_hand_value_no_aces(self):
        """Test hand value without aces."""
        from casino.services.game import GameService

        args = MagicMock()
        game = GameService(args)

        self.assertEqual(game._hand_value(["5H", "4H"]), 9)
        self.assertEqual(game._hand_value(["KH", "9H"]), 19)

    def test_hand_value_with_aces(self):
        """Test hand value with aces."""
        from casino.services.game import GameService

        args = MagicMock()
        game = GameService(args)

        # Soft hand
        self.assertEqual(game._hand_value(["AH", "8H"]), 19)

        # Hard hand (ace counts as 1)
        self.assertEqual(game._hand_value(["AH", "KH", "5H"]), 16)

        # Blackjack
        self.assertEqual(game._hand_value(["AH", "KH"]), 21)

    def test_bust(self):
        """Test bust detection."""
        from casino.services.game import GameService

        args = MagicMock()
        game = GameService(args)

        # Bust
        self.assertEqual(game._hand_value(["KH", "KH", "5H"]), 25)  # 10+10+5=25


class TestMessageParsing(unittest.TestCase):
    """Test message parsing."""

    def test_parse_message(self):
        """Test message parsing."""
        from casino.api.messages import parse_message

        # Valid message
        msg = parse_message({"type": "auth", "moniker": "test"})
        self.assertEqual(msg["type"], "auth")

        # Invalid - no type
        with self.assertRaises(ValueError):
            parse_message({"moniker": "test"})

    def test_create_message(self):
        """Test message creation."""
        from casino.api.messages import create_message, MessageType

        msg = create_message(MessageType.AUTH, moniker="test")
        self.assertEqual(msg["type"], "auth")
        self.assertEqual(msg["moniker"], "test")

    def test_error_message(self):
        """Test error message creation."""
        from casino.api.messages import error_message, ErrorCode

        msg = error_message(ErrorCode.NOT_AUTHENTICATED, "Please log in")
        self.assertEqual(msg["type"], "error")
        self.assertEqual(msg["code"], "not_authenticated")
        self.assertEqual(msg["message"], "Please log in")

    def test_pong_message(self):
        """Test pong message."""
        from casino.api.messages import pong_message

        msg = pong_message()
        self.assertEqual(msg["type"], "pong")
        self.assertIn("timestamp", msg)


def run_tests():
    """Run all tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestServerMocked))
    suite.addTests(loader.loadTestsFromTestCase(TestBlackjackGame))
    suite.addTests(loader.loadTestsFromTestCase(TestMessageParsing))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
