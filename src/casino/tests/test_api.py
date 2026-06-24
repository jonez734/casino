#!/usr/bin/env python3
# casino/tests/test_api.py
# Mock tests for casino API

import argparse
import asyncio
import json
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

sys.path.insert(0, "/home/opencode/data/work/casino/src")


class TestWebSocketServer(unittest.IsolatedAsyncioTestCase):
    """Test WebSocket server with service registry."""

    async def test_server_creation(self):
        """Test WebSocketServer can be created."""
        from bbsengine6.net import WebSocketServer

        server = WebSocketServer(host="127.0.0.1", port=18765)
        self.assertEqual(server.host, "127.0.0.1")
        self.assertEqual(server.port, 18765)
        self.assertFalse(server.is_running)

    async def test_service_registration(self):
        """Test service registry."""
        from bbsengine6.net import WebSocketServer

        server = WebSocketServer(host="127.0.0.1", port=18766)

        # Create mock service
        mock_service = AsyncMock()
        mock_service.handle_message = AsyncMock(return_value={"type": "response"})

        # Register service
        server.register_service(mock_service, ["test_message"])

        # Verify registration
        self.assertEqual(server.get_service("test_message"), mock_service)
        self.assertIsNone(server.get_service("other_message"))

        # List services
        services = server.list_services()
        self.assertIn("test_message", services)

    async def test_dispatch_message(self):
        """Test message dispatch to services."""
        from bbsengine6.net import WebSocketServer

        server = WebSocketServer(host="127.0.0.1", port=18767)

        # Create mock service
        mock_service = AsyncMock()
        mock_service.handle_message = AsyncMock(return_value={"type": "test_response"})

        server.register_service(mock_service, ["test"])

        # Dispatch message
        response = await server.dispatch_message(
            MagicMock(),  # websocket
            "default",  # path
            {"type": "test", "data": "value"},
        )

        self.assertEqual(response["type"], "test_response")
        mock_service.handle_message.assert_called_once()


class TestMessageHandler(unittest.IsolatedAsyncioTestCase):
    """Test message handler and routing."""

    async def test_session_manager(self):
        """Test session management."""
        from casino.api.handler import SessionManager

        sm = SessionManager()

        # Register session
        sm.register_session(1, "testuser")
        self.assertEqual(sm.get_moniker(1), "testuser")

        # Set table
        sm.set_table_moniker(1, "table5")
        self.assertEqual(sm.get_table_moniker(1), "table5")

        # Add spectator
        sm.add_spectator(5, 1)
        self.assertIn(1, sm.get_table_observers(5))

        # Unregister
        sm.unregister_session(1)
        self.assertIsNone(sm.get_moniker(1))

    async def test_auth_service_mock(self):
        """Test auth service with mocked database."""
        from casino.api.handler import AuthService, SessionManager

        # Create args with mock pool
        args = MagicMock()
        args.pool = MagicMock()  # Mock pool

        sm = SessionManager()
        auth_service = AuthService(args, sm)

        # Mock player service
        auth_service.player_service = MagicMock()
        auth_service.player_service.authenticate = MagicMock(
            return_value={"success": True, "moniker": "testuser", "balance": 1000}
        )
        auth_service.player_service.get_balance = MagicMock(return_value=1000)

        # Handle auth message
        ws = MagicMock()
        response = await auth_service._handle_auth(
            ws, {"type": "auth", "moniker": "testuser", "password": "testpass"}
        )

        self.assertTrue(response["success"])
        self.assertEqual(response["moniker"], "testuser")
        self.assertEqual(response["balance"], 1000)


class TestMessageTypes(unittest.TestCase):
    """Test message type definitions."""

    def test_message_types_exist(self):
        """Verify all message types are defined."""
        from casino.api.messages import MessageType

        required = [
            "AUTH",
            "AUTH_RESULT",
            "LIST_TABLES",
            "TABLE_LIST",
            "CREATE_TABLE",
            "JOIN_TABLE",
            "LEAVE_TABLE",
            "BET",
            "HIT",
            "STAND",
            "DOUBLE",
            "SPLIT",
            "CHAT_TABLE",
            "CHAT_GLOBAL",
            "EMOTE",
            "CHAT_MESSAGE",
            "PING",
            "PONG",
            "ERROR",
        ]

        for msg_type in required:
            self.assertTrue(hasattr(MessageType, msg_type))

    def test_game_phases(self):
        """Verify game phases."""
        from casino.api.messages import GamePhase

        phases = ["WAITING", "BETTING", "DEALING", "PLAYING", "SETTLING", "CLOSED"]
        for phase in phases:
            self.assertTrue(hasattr(GamePhase, phase))


class TestBlackjackLogic(unittest.IsolatedAsyncioTestCase):
    """Test blackjack game logic."""

    async def test_card_values(self):
        """Test card value calculation."""
        from casino.services.game import GameService

        args = MagicMock()
        game = GameService(args)

        # Test card values
        self.assertEqual(game._card_value("AH"), 11)  # Ace
        self.assertEqual(game._card_value("KH"), 10)  # Face cards
        self.assertEqual(game._card_value("9H"), 9)
        self.assertEqual(game._card_value("2H"), 2)

    def test_hand_value_ace_handling(self):
        """Test hand value with Ace adjustment."""
        from casino.services.game import GameService

        args = MagicMock()
        game = GameService(args)

        # No aces
        self.assertEqual(game._hand_value(["9H", "8H"]), 17)

        # One ace
        self.assertEqual(game._hand_value(["AH", "9H"]), 20)

        # Two aces (one counts as 1)
        self.assertEqual(game._hand_value(["AH", "AD", "9H"]), 21)

        # Bust with ace
        self.assertEqual(game._hand_value(["AH", "KH", "5H"]), 16)  # 11+10+5=26 -> 16

    def test_is_blackjack(self):
        """Test blackjack detection."""
        from casino.services.game import GameService

        args = MagicMock()
        game = GameService(args)

        # Natural blackjack
        self.assertTrue(game._is_blackjack(["AH", "KH"]))
        self.assertTrue(game._is_blackjack(["10H", "AH"]))
        self.assertTrue(game._is_blackjack(["QD", "AC"]))

        # Not blackjack
        self.assertFalse(game._is_blackjack(["AH", "KH", "5H"]))  # 3 cards
        self.assertFalse(game._is_blackjack(["AH", "9H"]))  # 20, not 21
        self.assertFalse(game._is_blackjack(["5H", "6H"]))  # 11


class TestDAL(unittest.IsolatedAsyncioTestCase):
    """Test Data Access Layer with mocks."""

    def test_player_dal_interface(self):
        """Test player DAL has required methods."""
        from casino.dal import player

        required = [
            "get_or_create_player",
            "get_player_by_moniker",
            "get_player_balance",
            "update_player_lastplayed",
        ]
        for method in required:
            self.assertTrue(hasattr(player, method))

    def test_table_dal_interface(self):
        """Test table DAL has required methods."""
        from casino.dal import table

        required = [
            "create_table",
            "get_table",
            "list_tables",
            "get_table_players",
            "add_player_to_table",
            "remove_player_from_table",
            "update_table",
            "reset_shoe",
        ]
        for method in required:
            self.assertTrue(hasattr(table, method))

    def test_game_dal_interface(self):
        """Test game DAL has required methods."""
        from casino.dal import game

        required = [
            "create_game",
            "get_active_game",
            "update_game_status",
            "create_hand",
            "update_hand_cards",
            "get_hand",
            "get_dealer_hand",
            "create_dealer_hand",
            "update_dealer_hand_cards",
            "get_or_create_dealer_hand",
        ]
        for method in required:
            self.assertTrue(hasattr(game, method))


class TestIntegration(unittest.IsolatedAsyncioTestCase):
    """Integration tests with mocked components."""

    async def test_full_auth_flow(self):
        """Test complete authentication flow."""
        from casino.api.handler import MessageRouter

        # Create mock args
        args = MagicMock()
        args.pool = MagicMock()

        # Create router
        router = MessageRouter(args)

        # Mock the services
        router.auth_service.player_service = MagicMock()
        router.auth_service.player_service.authenticate = MagicMock(
            return_value={"success": True, "moniker": "jam", "balance": 500}
        )
        router.auth_service.player_service.get_balance = MagicMock(return_value=500)

        # Create mock server and websocket
        mock_server = MagicMock()
        mock_ws = MagicMock()

        # Simulate auth
        response = await router.auth_service.handle_message(
            mock_server,
            mock_ws,
            "default",
            {"type": "auth", "moniker": "jam", "password": "12345"},
        )

        self.assertTrue(response["success"])
        self.assertEqual(response["moniker"], "jam")
        self.assertEqual(response["balance"], 500)


def run_tests():
    """Run all tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestWebSocketServer))
    suite.addTests(loader.loadTestsFromTestCase(TestMessageHandler))
    suite.addTests(loader.loadTestsFromTestCase(TestMessageTypes))
    suite.addTests(loader.loadTestsFromTestCase(TestBlackjackLogic))
    suite.addTests(loader.loadTestsFromTestCase(TestDAL))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegration))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
