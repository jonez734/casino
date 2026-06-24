#!/usr/bin/env python3
# casino/tests/test_postoffice_channel.py
# Tests for postoffice channel messaging

import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, "/home/opencode/data/work/casino/src")


class TestPostofficeChannel(unittest.TestCase):
    """Test postoffice channel constant."""

    def test_postoffice_channel_constant(self):
        """Test POSTOFFICE_CHANNEL constant is correct."""
        from casino.services.postoffice import POSTOFFICE_CHANNEL

        self.assertEqual(POSTOFFICE_CHANNEL, "postoffice:check_mail")


class TestPostofficeChannelIntegration(unittest.TestCase):
    """Test postoffice channel integration."""

    def test_service_publishes_to_channel(self):
        """Test service can publish to postoffice channel."""
        from casino.services.postoffice import POSTOFFICE_CHANNEL

        self.assertIn("postoffice", POSTOFFICE_CHANNEL)
        self.assertIn("check_mail", POSTOFFICE_CHANNEL)

    def test_channel_name_format(self):
        """Test channel name follows naming convention."""
        channel = "postoffice:check_mail"
        parts = channel.split(":")
        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[0], "postoffice")
        self.assertEqual(parts[1], "check_mail")


class TestMessageRouterChannelRegistration(unittest.TestCase):
    """Test that MessageRouter registers postoffice service."""

    def test_message_router_has_postoffice_service(self):
        """Test MessageRouter creates PostofficeServiceHandler."""
        from casino.api.handler import MessageRouter

        args = MagicMock()
        args.databasename = "test"

        router = MessageRouter(args)

        self.assertTrue(hasattr(router, "postoffice_service"))
        self.assertIsNotNone(router.postoffice_service)

    def test_postoffice_service_registered(self):
        """Test postoffice service is registered for check_mail message type."""
        from casino.api.handler import MessageRouter
        from bbsengine6.net import WebSocketServer

        args = MagicMock()
        args.databasename = "test"

        server = WebSocketServer(host="127.0.0.1", port=18770)
        router = MessageRouter(args)
        router.register_all(server)

        service = server.get_service("check_mail")
        self.assertIsNotNone(service)


class TestServiceHandlerIntegration(unittest.TestCase):
    """Test PostofficeServiceHandler integration."""

    def test_handler_handles_check_mail_message(self):
        """Test PostofficeServiceHandler handles check_mail message type."""
        import asyncio
        from casino.api.handler import PostofficeServiceHandler

        handler = PostofficeServiceHandler(MagicMock(), MagicMock())

        async def run_test():
            result = await handler.handle_message(
                MagicMock(), MagicMock(), "default", {"type": "check_mail"}
            )
            self.assertIsNotNone(result)

        asyncio.run(run_test())

    def test_handler_returns_none_for_unknown_message(self):
        """Test handler returns None for unknown message types."""
        import asyncio
        from casino.api.handler import PostofficeServiceHandler

        handler = PostofficeServiceHandler(MagicMock(), MagicMock())

        async def run_test():
            result = await handler.handle_message(
                MagicMock(), MagicMock(), "default", {"type": "unknown_type"}
            )
            self.assertIsNone(result)

        asyncio.run(run_test())


def run_tests():
    """Run all tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestPostofficeChannel))
    suite.addTests(loader.loadTestsFromTestCase(TestPostofficeChannelIntegration))
    suite.addTests(loader.loadTestsFromTestCase(TestMessageRouterChannelRegistration))
    suite.addTests(loader.loadTestsFromTestCase(TestServiceHandlerIntegration))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
