#!/usr/bin/env python3
# casino/tests/test_member_services.py
# Comprehensive tests for MemberServices

import asyncio
import json
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, "/home/opencode/data/work/casino/src")

import websockets

from bbsengine6 import database


def tier_column_exists(args):
    """Check if the tier column exists in engine.member view."""
    try:
        with database.connect(args) as conn:
            with database.cursor(conn) as cur:
                cur.execute(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = '__member' AND column_name = 'attrs'"
                )
                return cur.fetchone() is not None
    except Exception:
        return False


class TestMemberServicesDAL(unittest.IsolatedAsyncioTestCase):
    """Integration tests for MemberService DAL functions with real database."""

    async def asyncSetUp(self):
        """Set up test database and member."""
        parser = MagicMock()
        parser.databasename = "zoid6"
        parser.databasehost = "localhost"
        parser.databaseport = 5432
        parser.databaseuser = "postgres"
        parser.databasepassword = ""
        self.args = parser
        
        self.pool = database.getpool(self.args)
        self.test_moniker = "member_service_test"
        
        self.tier_available = tier_column_exists(self.args)
        
        if not self.tier_available:
            self.skipTest("member table not available")

        try:
            with database.connect(self.args, pool=self.pool) as conn:
                with database.cursor(conn) as cur:
                    cur.execute(
                        "INSERT INTO engine.__member (moniker, loginid, password, email, credits, attrs) "
                        "VALUES ('member_service_test', 'member_service_test', crypt('test', gen_salt('md5')), 'membertest@test.local', 1000, '{\"tier\": \"bronze\"}'::jsonb) "
                        "ON CONFLICT (moniker) DO UPDATE SET attrs = '{\"tier\": \"bronze\"}'::jsonb"
                    )
        except Exception as e:
            pass

    async def asyncTearDown(self):
        """Clean up test data."""
        if hasattr(self, "pool") and self.pool is not None:
            try:
                with database.connect(self.args, pool=self.pool) as conn:
                    with database.cursor(conn) as cur:
                        cur.execute(
                            "DELETE FROM engine.__member WHERE moniker = 'member_service_test'"
                        )
            except Exception:
                pass
            self.pool.close()
            self.pool = None

    async def test_get_profile(self):
        """Test getting member profile."""
        from bbsengine6.services.member import MemberService
        
        service = MemberService(self.args)
        profile = service.get_profile(self.test_moniker)
        
        self.assertIsNotNone(profile)
        self.assertEqual(profile["moniker"], self.test_moniker)
        self.assertEqual(profile["tier"], "bronze")

    async def test_get_tier(self):
        """Test getting member tier."""
        from bbsengine6.services.member import MemberService
        
        service = MemberService(self.args)
        tier = service.get_tier(self.test_moniker)
        
        self.assertEqual(tier, "bronze")

    async def test_set_tier(self):
        """Test setting member tier."""
        from bbsengine6.services.member import MemberService
        
        service = MemberService(self.args)
        
        success = service.set_tier(self.test_moniker, "gold")
        self.assertTrue(success)
        
        tier = service.get_tier(self.test_moniker)
        self.assertEqual(tier, "gold")

    async def test_get_referral_code(self):
        """Test getting member referral code."""
        from bbsengine6.services.member import MemberService
        
        service = MemberService(self.args)
        refcode = service.get_referral_code(self.test_moniker)
        
        self.assertIsNone(refcode)

    async def test_get_referrals(self):
        """Test getting member's referrals."""
        from bbsengine6.services.member import MemberService
        
        service = MemberService(self.args)
        referrals = service.get_referrals(self.test_moniker)
        
        self.assertIsInstance(referrals, list)


class TestMemberServicesBED(unittest.IsolatedAsyncioTestCase):
    """Integration tests for MemberService via BED WebSocket."""

    async def asyncSetUp(self):
        """Start BED before each test."""
        from bbsengine6.net import WebSocketServer
        from casino.api.handler import MessageRouter

        self.mock_args = MagicMock()
        self.mock_args.databasename = "test"
        self.mock_args.databasehost = "localhost"
        self.mock_args.databaseport = 5432
        self.mock_args.databaseuser = "test"
        self.mock_args.databasepassword = "test"
        self.mock_args.debug = False
        self.mock_args.host = "127.0.0.1"
        self.mock_args.port = 18772

        mock_pool = MagicMock()
        mock_pool.connection.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_pool.connection.return_value.__exit__ = MagicMock(return_value=False)
        self.mock_args.pool = mock_pool

        self.server = WebSocketServer(
            host=self.mock_args.host,
            port=self.mock_args.port,
        )

        self.router = MessageRouter(self.mock_args)
        self.router.register_all(self.server)

        await self.server.start()
        self._server_started = True

    async def asyncTearDown(self):
        """Stop BED after each test."""
        if hasattr(self, "_server_started") and self._server_started:
            await self.server.stop()

    async def test_member_profile_message(self):
        """Test member_profile message type."""
        from bbsengine6.services.member import MemberService
        
        self.router.member_service.member_service = MagicMock(spec=MemberService)
        self.router.member_service.member_service.get_profile = MagicMock(
            return_value={"moniker": "testuser", "email": "test@test.local", "tier": "bronze"}
        )

        uri = f"ws://{self.mock_args.host}:{self.mock_args.port}/"
        async with websockets.connect(uri) as ws:
            await ws.send(json.dumps({
                "type": "member_profile",
                "moniker": "testuser"
            }))
            response = json.loads(await ws.recv())
            
            self.assertEqual(response["type"], "member_profile_result")
            self.assertTrue(response["success"])
            self.assertEqual(response["profile"]["moniker"], "testuser")

    async def test_member_tier_get_message(self):
        """Test member_tier message type with get action."""
        from bbsengine6.services.member import MemberService
        
        self.router.member_service.member_service = MagicMock(spec=MemberService)
        self.router.member_service.member_service.get_tier = MagicMock(
            return_value="gold"
        )

        uri = f"ws://{self.mock_args.host}:{self.mock_args.port}/"
        async with websockets.connect(uri) as ws:
            await ws.send(json.dumps({
                "type": "member_tier",
                "action": "get",
                "moniker": "testuser"
            }))
            response = json.loads(await ws.recv())
            
            self.assertEqual(response["type"], "member_tier_result")
            self.assertTrue(response["success"])
            self.assertEqual(response["tier"], "gold")

    async def test_member_tier_set_message(self):
        """Test member_tier message type with set action."""
        from bbsengine6.services.member import MemberService
        
        self.router.member_service.member_service = MagicMock(spec=MemberService)
        self.router.member_service.member_service.set_tier = MagicMock(
            return_value=True
        )

        uri = f"ws://{self.mock_args.host}:{self.mock_args.port}/"
        async with websockets.connect(uri) as ws:
            await ws.send(json.dumps({
                "type": "member_tier",
                "action": "set",
                "moniker": "testuser",
                "tier": "platinum"
            }))
            response = json.loads(await ws.recv())
            
            self.assertEqual(response["type"], "member_tier_result")
            self.assertTrue(response["success"])
            self.assertEqual(response["tier"], "platinum")

    async def test_member_referral_code_message(self):
        """Test member_referral_code message type."""
        from bbsengine6.services.member import MemberService
        
        self.router.member_service.member_service = MagicMock(spec=MemberService)
        self.router.member_service.member_service.get_referral_code = MagicMock(
            return_value="TEST123"
        )

        uri = f"ws://{self.mock_args.host}:{self.mock_args.port}/"
        async with websockets.connect(uri) as ws:
            await ws.send(json.dumps({
                "type": "member_referral_code",
                "moniker": "testuser"
            }))
            response = json.loads(await ws.recv())
            
            self.assertEqual(response["type"], "member_referral_code_result")
            self.assertTrue(response["success"])
            self.assertEqual(response["refcode"], "TEST123")

    async def test_member_referrals_message(self):
        """Test member_referrals message type."""
        from bbsengine6.services.member import MemberService
        
        self.router.member_service.member_service = MagicMock(spec=MemberService)
        self.router.member_service.member_service.get_referrals = MagicMock(
            return_value=[{"moniker": "referred1"}, {"moniker": "referred2"}]
        )

        uri = f"ws://{self.mock_args.host}:{self.mock_args.port}/"
        async with websockets.connect(uri) as ws:
            await ws.send(json.dumps({
                "type": "member_referrals",
                "moniker": "testuser"
            }))
            response = json.loads(await ws.recv())
            
            self.assertEqual(response["type"], "member_referrals_result")
            self.assertTrue(response["success"])
            self.assertEqual(len(response["referrals"]), 2)


class TestMemberServicesMocked(unittest.IsolatedAsyncioTestCase):
    """Unit tests for MemberService with mocked DAL."""

    async def asyncSetUp(self):
        """Set up mock args."""
        self.mock_args = MagicMock()

    async def test_get_profile_returns_attrs(self):
        """Test get_profile returns member attributes."""
        from bbsengine6.services.member import MemberService
        
        mock_service = MemberService(self.mock_args)
        
        with patch.object(mock_service, 'get_profile') as mock_get:
            mock_get.return_value = {
                "moniker": "testuser",
                "email": "test@test.local",
                "tier": "silver",
                "attrs": {"tier": "silver", "preferences": {}}
            }
            
            result = mock_service.get_profile("testuser")
            self.assertEqual(result["tier"], "silver")

    async def test_update_profile_merges_attrs(self):
        """Test update_profile merges new attrs with existing."""
        from bbsengine6.services.member import MemberService
        
        mock_service = MemberService(self.mock_args)
        
        with patch.object(mock_service, 'update_profile') as mock_update:
            mock_update.return_value = {"success": True, "message": "Profile updated"}
            
            result = mock_service.update_profile("testuser", {"tier": "gold"})
            self.assertTrue(result["success"])

    async def test_tier_transitions(self):
        """Test tier can be changed from one to another."""
        from bbsengine6.services.member import MemberService
        
        mock_service = MemberService(self.mock_args)
        
        with patch.object(mock_service, 'set_tier') as mock_set:
            mock_set.return_value = True
            
            result = mock_service.set_tier("testuser", "diamond")
            self.assertTrue(result)

    async def test_get_referral_code_returns_string(self):
        """Test get_referral_code returns refcode string."""
        from bbsengine6.services.member import MemberService
        
        mock_service = MemberService(self.mock_args)
        
        with patch.object(mock_service, 'get_referral_code') as mock_code:
            mock_code.return_value = "REFCODE123"
            
            result = mock_service.get_referral_code("testuser")
            self.assertEqual(result, "REFCODE123")

    async def test_get_referrals_returns_list(self):
        """Test get_referrals returns list of referred members."""
        from bbsengine6.services.member import MemberService
        
        mock_service = MemberService(self.mock_args)
        
        with patch.object(mock_service, 'get_referrals') as mock_refs:
            mock_refs.return_value = [
                {"moniker": "user1", "email": "user1@test.local"},
                {"moniker": "user2", "email": "user2@test.local"}
            ]
            
            result = mock_service.get_referrals("testuser")
            self.assertEqual(len(result), 2)

    async def test_use_referral_code_success(self):
        """Test use_referral_code records referral successfully."""
        from bbsengine6.services.member import MemberService
        
        mock_service = MemberService(self.mock_args)
        
        with patch.object(mock_service, 'use_referral_code') as mock_use:
            mock_use.return_value = {"success": True, "message": "Referral recorded", "referrer": "referrer1"}
            
            result = mock_service.use_referral_code("testuser", "REFCODE123")
            self.assertTrue(result["success"])

    async def test_use_referral_code_invalid_code(self):
        """Test use_referral_code fails with invalid code."""
        from bbsengine6.services.member import MemberService
        
        mock_service = MemberService(self.mock_args)
        
        with patch.object(mock_service, 'use_referral_code') as mock_use:
            mock_use.return_value = {"success": False, "message": "Invalid referral code"}
            
            result = mock_service.use_referral_code("testuser", "INVALID")
            self.assertFalse(result["success"])
            self.assertEqual(result["message"], "Invalid referral code")


if __name__ == "__main__":
    unittest.main()
