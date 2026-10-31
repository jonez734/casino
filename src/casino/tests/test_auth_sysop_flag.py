"""Casino's auth_result carries is_sysop.

Bed reports sysop status in its own auth and reconnect replies. Casino's
``auth_result`` success payload also reports it, so the menu can show sysop
commands from the first reply.
"""

import unittest
from unittest.mock import MagicMock, patch


class TestAuthResultIsSysop(unittest.IsolatedAsyncioTestCase):
    async def _auth(self, is_sysop: bool) -> dict:
        from casino.api.handler import AuthService, SessionManager

        args = MagicMock()
        args.pool = MagicMock()
        args.databasename = "test"

        service = AuthService(args, SessionManager())
        service.player_service = MagicMock()
        service.player_service.authenticate = MagicMock(
            return_value={"success": True, "moniker": "sysop1", "balance": 500}
        )
        service.player_service.get_balance = MagicMock(return_value=500)

        ws = MagicMock()
        with patch("casino.api.handler.member.issysop", return_value=is_sysop), \
             patch("casino.api.handler.deliver_pending_on_connect", return_value=[]), \
             patch("casino.api.handler.get_unread_count", return_value=0):
            return await service._handle_auth(
                ws, {"type": "auth", "moniker": "sysop1", "password": "pw"}
            )

    async def test_sysop_member_gets_is_sysop_true(self):
        response = await self._auth(is_sysop=True)
        self.assertTrue(response["success"])
        self.assertIs(response["is_sysop"], True)

    async def test_regular_member_gets_is_sysop_false(self):
        response = await self._auth(is_sysop=False)
        self.assertTrue(response["success"])
        self.assertIs(response["is_sysop"], False)

    async def test_failed_auth_has_no_is_sysop_field(self):
        from casino.api.handler import AuthService, SessionManager

        args = MagicMock()
        args.pool = MagicMock()
        service = AuthService(args, SessionManager())
        service.player_service = MagicMock()
        service.player_service.authenticate = MagicMock(
            return_value={"success": False, "message": "invalid password"}
        )
        response = await service._handle_auth(
            MagicMock(), {"type": "auth", "moniker": "x", "password": "bad"}
        )
        self.assertFalse(response["success"])
        self.assertNotIn("is_sysop", response)


if __name__ == "__main__":
    unittest.main()
