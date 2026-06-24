#!/usr/bin/env python3
# casino/tests/test_postoffice_manual_check.py
# Tests for manual mail check via message type

import pytest
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, "/home/opencode/data/work/mistermcfeely/src")
sys.path.insert(0, "/home/opencode/data/work/casino/src")


@pytest.mark.integration
class TestHandleCheckMail(unittest.IsolatedAsyncioTestCase):
    """Test handle_check_mail method."""

    async def test_handle_check_mail_no_mailboxes(self):
        """Test manual check with no mailboxes configured."""
        from postoffice.service import PostofficeService

        service = PostofficeService(config={
            "enabled": False,
            "poll_interval": 30,
            "mailboxes": []
        })

        result = await service.handle_check_mail("testuser")

        self.assertTrue(result["success"])
        self.assertEqual(result["mailboxes_checked"], 0)
        self.assertEqual(result["total_unread"], 0)
        self.assertEqual(len(result["errors"]), 0)

    async def test_handle_check_mail_with_mailboxes(self):
        """Test manual check with mailboxes configured."""
        from postoffice.service import PostofficeService

        mailboxes = [
            {"host": "imap.test.com", "username": "user", "password": "pass"}
        ]
        service = PostofficeService(config={
            "enabled": False,
            "poll_interval": 30,
            "mailboxes": mailboxes
        })

        with patch.object(service, "_check_mailbox_count", return_value=5):
            result = await service.handle_check_mail("testuser")

        self.assertTrue(result["success"])
        self.assertEqual(result["mailboxes_checked"], 1)
        self.assertEqual(result["total_unread"], 5)

    async def test_handle_check_mail_multiple_mailboxes(self):
        """Test manual check with multiple mailboxes."""
        from postoffice.service import PostofficeService

        mailboxes = [
            {"host": "imap1.test.com", "username": "u1", "password": "p1"},
            {"host": "imap2.test.com", "username": "u2", "password": "p2"},
        ]
        service = PostofficeService(config={
            "enabled": False,
            "poll_interval": 30,
            "mailboxes": mailboxes
        })

        with patch.object(service, "_check_mailbox_count", side_effect=[3, 7]):
            result = await service.handle_check_mail("testuser")

        self.assertTrue(result["success"])
        self.assertEqual(result["mailboxes_checked"], 2)
        self.assertEqual(result["total_unread"], 10)

    async def test_handle_check_mail_handles_errors(self):
        """Test manual check handles mailbox errors."""
        from postoffice.service import PostofficeService

        mailboxes = [
            {"host": "imap1.test.com", "username": "u1", "password": "p1"},
            {"host": "imap2.test.com", "username": "u2", "password": "p2"},
        ]
        service = PostofficeService(config={
            "enabled": False,
            "poll_interval": 30,
            "mailboxes": mailboxes
        })

        with patch.object(service, "_check_mailbox_count", side_effect=[3, Exception("Connection failed")]):
            result = await service.handle_check_mail("testuser")

        self.assertTrue(result["success"])
        self.assertEqual(result["mailboxes_checked"], 2)
        self.assertEqual(result["total_unread"], 3)
        self.assertEqual(len(result["errors"]), 1)


@pytest.mark.integration
class TestCheckMailboxCount(unittest.IsolatedAsyncioTestCase):
    """Test _check_mailbox_count method."""

    async def test_check_mailbox_count_returns_zero_on_error(self):
        """Test _check_mailbox_count returns 0 on error."""
        from postoffice.service import PostofficeService, MailboxConfig

        mb = MailboxConfig(host="invalid.test.com", username="user", password="pass")
        service = PostofficeService(config={"enabled": False, "poll_interval": 30, "mailboxes": []})

        with patch("imaplib.IMAP4_SSL", side_effect=Exception("Connection refused")):
            count = service._check_mailbox_count(mb)

        self.assertEqual(count, 0)

    async def test_check_mailbox_count_parses_unseen(self):
        """Test _check_mailbox_count correctly counts unseen messages."""
        from postoffice.service import PostofficeService, MailboxConfig

        mb = MailboxConfig(host="mail.test.com", username="user", password="pass")
        service = PostofficeService(config={"enabled": False, "poll_interval": 30, "mailboxes": []})

        mock_conn = MagicMock()
        mock_conn.search.return_value = ("OK", [b"1 2 3 4 5"])

        with patch("imaplib.IMAP4_SSL", return_value=mock_conn):
            count = service._check_mailbox_count(mb)

        self.assertEqual(count, 5)

    async def test_check_mailbox_count_no_unseen(self):
        """Test _check_mailbox_count with no unseen messages."""
        from postoffice.service import PostofficeService, MailboxConfig

        mb = MailboxConfig(host="mail.test.com", username="user", password="pass")
        service = PostofficeService(config={"enabled": False, "poll_interval": 30, "mailboxes": []})

        mock_conn = MagicMock()
        mock_conn.search.return_value = ("OK", [b""])

        with patch("imaplib.IMAP4_SSL", return_value=mock_conn):
            count = service._check_mailbox_count(mb)

        self.assertEqual(count, 0)


@pytest.mark.integration
class TestPostofficeServiceHandler(unittest.IsolatedAsyncioTestCase):
    """Test PostofficeServiceHandler in API."""

    async def test_handler_returns_error_for_unauthenticated(self):
        """Test handler returns error for unauthenticated session."""
        from casino.api.handler import PostofficeServiceHandler, SessionManager

        session_manager = SessionManager()
        session_manager.register_session(1, "testuser")

        args = MagicMock()
        args.databasename = "test"

        handler = PostofficeServiceHandler(args, session_manager)

        mock_server = MagicMock()
        mock_ws = MagicMock()

        result = await handler.handle_message(
            mock_server, mock_ws, "default", {"type": "check_mail"}
        )

        self.assertEqual(result["code"], "not_authenticated")

    async def test_handler_processes_check_mail(self):
        """Test handler processes check_mail message."""
        from casino.api.handler import PostofficeServiceHandler, SessionManager

        session_manager = SessionManager()
        session_manager.register_session(1, "testuser")

        args = MagicMock()
        args.databasename = "test"

        handler = PostofficeServiceHandler(args, session_manager)
        handler.postoffice_service = MagicMock()
        handler.postoffice_service.handle_check_mail = AsyncMock(return_value={
            "success": True,
            "mailboxes_checked": 2,
            "total_unread": 5,
            "errors": []
        })

        mock_server = MagicMock()
        mock_ws = MagicMock()

        with patch("builtins.id", return_value=1):
            result = await handler.handle_message(
                mock_server, mock_ws, "default", {"type": "check_mail"}
            )

        self.assertEqual(result["type"], "check_mail_result")
        self.assertTrue(result["success"])
        self.assertEqual(result["mailboxes_checked"], 2)
        self.assertEqual(result["total_unread"], 5)


def run_tests():
    """Run all tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestHandleCheckMail))
    suite.addTests(loader.loadTestsFromTestCase(TestCheckMailboxCount))
    suite.addTests(loader.loadTestsFromTestCase(TestPostofficeServiceHandler))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
