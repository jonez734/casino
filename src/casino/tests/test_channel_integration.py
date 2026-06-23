#!/usr/bin/env python3
# casino/tests/test_channel_integration.py
# Integration tests for channel subscription system

import argparse
import asyncio
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, "/home/opencode/data/work/casino/src")


class TestChannelSubscriptionIntegration(unittest.IsolatedAsyncioTestCase):
    """Integration tests for channel subscription in casino API."""

    async def asyncSetUp(self):
        """Set up test fixtures."""
        from bbsengine6.net import ChannelState
        from casino.api.handler import MessageRouter, SessionManager

        # Create args mock
        self.args = MagicMock()
        self.args.pool = MagicMock()
        self.args.databasename = "test"

        # Create MessageRouter with channel state
        self.router = MessageRouter(self.args)
        self.sessions = self.router.sessions
        self.channel_state = self.router.channel_state

    async def test_auth_auto_subscribes_to_member_channel(self):
        """Auth should auto-subscribe to member:{moniker} channel."""
        from bbsengine6.net import channel_get_session_channels
        from casino.api.handler import AuthService

        # Create auth service with channel state
        auth_service = AuthService(self.args, self.sessions, self.channel_state)

        # Mock player service
        auth_service.player_service = MagicMock()
        auth_service.player_service.authenticate = MagicMock(
            return_value={"success": True, "moniker": "alice", "balance": 1000}
        )
        auth_service.player_service.get_balance = MagicMock(return_value=1000)

        # Mock websocket - session_id will be id(ws)
        ws = MagicMock()
        session_id = id(ws)

        # Handle auth
        response = await auth_service._handle_auth(
            ws, {"type": "auth", "moniker": "alice", "password": "testpass"}
        )

        # Verify auth success
        self.assertTrue(response["success"])

        # Verify auto-subscription to member:alice
        channels = channel_get_session_channels(self.channel_state, session_id)
        self.assertIn("member:alice", channels)

    async def test_join_table_auto_subscribes_to_table_channel(self):
        """Join table should auto-subscribe to casino:table:{moniker}."""
        from bbsengine6.net import channel_get_session_channels
        from casino.api.handler import TableServiceHandler

        # Create table service with channel state
        table_service = TableServiceHandler(self.args, self.sessions, self.channel_state)

        # Mock table service
        table_service.table_service = MagicMock()
        table_service.table_service.join_table = MagicMock(
            return_value={"success": True, "moniker": "blackjack-1", "message": "Joined"}
        )

        # Register session
        session_id = 12345
        self.sessions.register_session(session_id, "alice")

        # Handle join table
        response = await table_service._handle_join_table(
            session_id, {"moniker": "blackjack-1"}
        )

        # Verify join success - response has type "joined_table"
        self.assertEqual(response["type"], "joined_table")

        # Verify auto-subscription to casino:table:blackjack-1
        channels = channel_get_session_channels(self.channel_state, session_id)
        self.assertIn("casino:table:blackjack-1", channels)

    async def test_watch_table_auto_subscribes_to_table_channel(self):
        """Watch table should auto-subscribe to casino:table:{moniker}."""
        from bbsengine6.net import channel_get_session_channels
        from casino.api.handler import TableServiceHandler

        # Create table service with channel state
        table_service = TableServiceHandler(self.args, self.sessions, self.channel_state)

        # Mock async table dal
        with patch("casino.api.handler.async_dal_table.get_table") as mock_get_table:
            mock_get_table.return_value = {"moniker": "blackjack-1", "status": "open"}

            # Register session
            session_id = 12345
            self.sessions.register_session(session_id, "bob")

            # Handle watch table
            response = await table_service._handle_watch_table(
                session_id, {"moniker": "blackjack-1"}
            )

            # Verify watch success
            self.assertEqual(response["type"], "watching_table")

            # Verify auto-subscription to casino:table:blackjack-1
            channels = channel_get_session_channels(self.channel_state, session_id)
            self.assertIn("casino:table:blackjack-1", channels)

    async def test_leave_table_unsubscribes_from_table_channel(self):
        """Leave table should unsubscribe from casino:table:{moniker}."""
        from bbsengine6.net import channel_get_session_channels, channel_subscribe
        from casino.api.handler import TableServiceHandler

        # Create table service with channel state
        table_service = TableServiceHandler(self.args, self.sessions, self.channel_state)

        # Pre-subscribe to table channel
        session_id = 12345
        self.sessions.register_session(session_id, "alice")
        self.sessions.set_table_moniker(session_id, "blackjack-1")
        channel_subscribe(self.channel_state, session_id, "casino:table:blackjack-1")

        # Mock table service
        table_service.table_service = MagicMock()
        table_service.table_service.leave_table = MagicMock(
            return_value={"success": True, "message": "Left"}
        )

        # Handle leave table
        response = await table_service._handle_leave_table(
            session_id, {"moniker": "blackjack-1"}
        )

        # Verify leave success - response has type "left_table"
        self.assertEqual(response["type"], "left_table")

        # Verify unsubscribed from table channel
        channels = channel_get_session_channels(self.channel_state, session_id)
        self.assertNotIn("casino:table:blackjack-1", channels)

    async def test_stop_watching_unsubscribes_from_table_channel(self):
        """Stop watching should unsubscribe from casino:table:{moniker}."""
        from bbsengine6.net import channel_get_session_channels, channel_subscribe
        from casino.api.handler import TableServiceHandler

        # Create table service with channel state
        table_service = TableServiceHandler(self.args, self.sessions, self.channel_state)

        # Pre-subscribe to table channel
        session_id = 12345
        self.sessions.register_session(session_id, "bob")
        self.sessions.add_spectator("blackjack-1", session_id)
        channel_subscribe(self.channel_state, session_id, "casino:table:blackjack-1")

        # Handle stop watching
        response = await table_service._handle_stop_watching(
            session_id, {"moniker": "blackjack-1"}
        )

        # Verify success
        self.assertEqual(response["type"], "stopped_watching")

        # Verify unsubscribed from table channel
        channels = channel_get_session_channels(self.channel_state, session_id)
        self.assertNotIn("casino:table:blackjack-1", channels)

    async def test_disconnect_unsubscribes_all_channels(self):
        """Session disconnect should unsubscribe from all channels."""
        from bbsengine6.net import channel_get_session_channels, channel_subscribe
        from casino.api.handler import SessionManager

        # Register session and subscribe to multiple channels
        session_id = 12345
        self.sessions.register_session(session_id, "alice")
        channel_subscribe(self.channel_state, session_id, "member:alice")
        channel_subscribe(self.channel_state, session_id, "casino:table:blackjack-1")
        channel_subscribe(self.channel_state, session_id, "system:shout")

        # Verify subscriptions
        channels = channel_get_session_channels(self.channel_state, session_id)
        self.assertEqual(len(channels), 3)

        # Unregister session (should unsubscribe all)
        self.router.unregister_session(session_id)

        # Verify all subscriptions removed
        channels = channel_get_session_channels(self.channel_state, session_id)
        self.assertEqual(len(channels), 0)

    async def test_subscribe_channel_message_type(self):
        """subscribe_channel message type should work."""
        from casino.api.handler import ChannelServiceHandler

        # Create channel service
        channel_service = ChannelServiceHandler(
            self.args, self.sessions, self.channel_state, MagicMock()
        )

        # Register session
        session_id = 12345
        self.sessions.register_session(session_id, "alice")

        # Handle subscribe_channel
        response = await channel_service._handle_subscribe(
            session_id, {"channel": "system:shout"}
        )

        # Verify subscription
        self.assertEqual(response["type"], "subscribed")
        self.assertEqual(response["channel"], "system:shout")

        # Verify in session channels
        from bbsengine6.net import channel_get_session_channels
        channels = channel_get_session_channels(self.channel_state, session_id)
        self.assertIn("system:shout", channels)

    async def test_unsubscribe_channel_message_type(self):
        """unsubscribe_channel message type should work."""
        from bbsengine6.net import channel_get_session_channels, channel_subscribe
        from casino.api.handler import ChannelServiceHandler

        # Pre-subscribe
        session_id = 12345
        self.sessions.register_session(session_id, "alice")
        channel_subscribe(self.channel_state, session_id, "system:shout")

        # Create channel service
        channel_service = ChannelServiceHandler(
            self.args, self.sessions, self.channel_state, MagicMock()
        )

        # Handle unsubscribe_channel
        response = await channel_service._handle_unsubscribe(
            session_id, {"channel": "system:shout"}
        )

        # Verify unsubscribed
        self.assertEqual(response["type"], "unsubscribed")

        # Verify not in session channels
        channels = channel_get_session_channels(self.channel_state, session_id)
        self.assertNotIn("system:shout", channels)

    async def test_get_subscriptions_message_type(self):
        """get_subscriptions message type should work."""
        from bbsengine6.net import channel_subscribe
        from casino.api.handler import ChannelServiceHandler

        # Pre-subscribe to channels
        session_id = 12345
        self.sessions.register_session(session_id, "alice")
        channel_subscribe(self.channel_state, session_id, "member:alice")
        channel_subscribe(self.channel_state, session_id, "casino:table:blackjack-1")

        # Create channel service
        channel_service = ChannelServiceHandler(
            self.args, self.sessions, self.channel_state, MagicMock()
        )

        # Handle get_subscriptions
        response = await channel_service._handle_get_subscriptions(session_id)

        # Verify response
        self.assertEqual(response["type"], "subscriptions")
        self.assertIn("member:alice", response["channels"])
        self.assertIn("casino:table:blackjack-1", response["channels"])

    async def test_channel_service_registered(self):
        """Channel service should be registered in MessageRouter."""
        # Create mock server
        mock_server = MagicMock()

        # Register all services
        self.router.register_all(mock_server)

        # Verify channel service was created
        self.assertIsNotNone(self.router.channel_service)

        # Verify register_service was called for channel message types
        mock_server.register_service.assert_any_call(
            self.router.channel_service,
            ["subscribe_channel", "unsubscribe_channel", "get_subscriptions"],
        )


if __name__ == "__main__":
    unittest.main()
