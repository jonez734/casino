#!/usr/bin/env python3
# casino/tests/test_channel_integration.py
# Channel-subscription integration tests that survive the casino API.
#
# Casino's bundled ChannelServiceHandler was decoupled into
# ``bbsengine6.channel.api.handler`` (commit bfb2a07). The remaining
# tests in this file cover the surfaces casino still owns:
#
# - ``MessageRouter.unregister_session`` clearing every channel
#   subscription for the disconnected session.
# - The canonical channel subscription handlers in
#   ``bbsengine6.channel.api.handler``, exercised directly because
#   the router no longer wires them in casino's register_all path.

import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, "/home/opencode/data/work/casino/src")


class TestChannelSubscriptionIntegration(unittest.IsolatedAsyncioTestCase):
    """Channel subscription integration tests that survive the casino API."""

    async def asyncSetUp(self):
        """Set up test fixtures."""
        from casino.api.handler import MessageRouter

        self.args = MagicMock()
        self.args.pool = MagicMock()
        self.args.databasename = "test"

        self.router = MessageRouter(self.args)
        self.sessions = self.router.sessions
        self.channel_state = self.router.channel_state

    async def test_disconnect_unsubscribes_all_channels(self):
        """Session disconnect should unsubscribe from all channels."""
        from bbsengine6.net import channel_get_session_channels, channel_subscribe

        session_id = 12345
        self.sessions.register_session(session_id, "alice")
        channel_subscribe(self.channel_state, session_id, "member:alice")
        channel_subscribe(self.channel_state, session_id, "casino:table:blackjack-1")
        channel_subscribe(self.channel_state, session_id, "system:shout")

        channels = channel_get_session_channels(self.channel_state, session_id)
        self.assertEqual(len(channels), 3)

        self.router.unregister_session(session_id)

        channels = channel_get_session_channels(self.channel_state, session_id)
        self.assertEqual(len(channels), 0)

    async def test_subscribe_channel_message_type(self):
        """subscribe_channel message type should work."""
        from bbsengine6.channel.api.handler import ChannelServiceHandler
        from bbsengine6.net import channel_get_session_channels

        channel_service = ChannelServiceHandler(
            self.args, self.sessions, self.channel_state
        )

        session_id = 12345
        self.sessions.register_session(session_id, "alice")

        response = await channel_service._handle_subscribe(
            session_id, {"channel": "system:shout"}
        )

        self.assertEqual(response["type"], "subscribed")
        self.assertEqual(response["channel"], "system:shout")
        channels = channel_get_session_channels(self.channel_state, session_id)
        self.assertIn("system:shout", channels)

    async def test_unsubscribe_channel_message_type(self):
        """unsubscribe_channel message type should work."""
        from bbsengine6.channel.api.handler import ChannelServiceHandler
        from bbsengine6.net import channel_get_session_channels, channel_subscribe

        session_id = 12345
        self.sessions.register_session(session_id, "alice")
        channel_subscribe(self.channel_state, session_id, "system:shout")

        channel_service = ChannelServiceHandler(
            self.args, self.sessions, self.channel_state
        )

        response = await channel_service._handle_unsubscribe(
            session_id, {"channel": "system:shout"}
        )

        self.assertEqual(response["type"], "unsubscribed")
        channels = channel_get_session_channels(self.channel_state, session_id)
        self.assertNotIn("system:shout", channels)

    async def test_get_subscriptions_message_type(self):
        """get_subscriptions message type should work."""
        from bbsengine6.channel.api.handler import ChannelServiceHandler
        from bbsengine6.net import channel_subscribe

        session_id = 12345
        self.sessions.register_session(session_id, "alice")
        channel_subscribe(self.channel_state, session_id, "member:alice")
        channel_subscribe(self.channel_state, session_id, "casino:table:blackjack-1")

        channel_service = ChannelServiceHandler(
            self.args, self.sessions, self.channel_state
        )

        response = await channel_service._handle_get_subscriptions(session_id)

        self.assertEqual(response["type"], "subscriptions")
        self.assertIn("member:alice", response["channels"])
        self.assertIn("casino:table:blackjack-1", response["channels"])

    async def test_router_does_not_own_channel_service(self):
        """Casino's router registers a fixed set of services; the
        channel subscription service is intentionally not among them
        (commit bfb2a07 moved it to ``bbsengine6.channel.api``). The
        bed-side wiring takes over once bed.json enables it.
        """
        mock_server = MagicMock()
        self.router.register_all(mock_server)
        self.assertFalse(hasattr(self.router, "channel_service"))


if __name__ == "__main__":
    unittest.main()
