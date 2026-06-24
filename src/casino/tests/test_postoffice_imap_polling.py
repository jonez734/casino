#!/usr/bin/env python3
# casino/tests/test_postoffice_imap_polling.py
# Tests for IMAP connection and polling

import imaplib
import pytest
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, "/home/opencode/data/work/casino/src")
sys.path.insert(0, "/home/opencode/data/work/mistermcfeely/src")


@pytest.mark.integration
class TestIMAPConnection(unittest.TestCase):
    """Test IMAP connection functionality."""

    def test_check_mailbox_sync_with_ssl(self):
        """Test _check_mailbox_sync with SSL connection."""
        from postoffice.service import PostofficeService, MailboxConfig

        mb = MailboxConfig(host="imap.test.com", username="user", password="pass", use_ssl=True)
        service = PostofficeService(config={"enabled": False, "poll_interval": 30, "mailboxes": []})

        mock_conn = MagicMock()
        mock_conn.search.return_value = ("OK", [b"1 2 3"])

        with patch("imaplib.IMAP4_SSL", return_value=mock_conn) as mock_ssl:
            with patch.object(service, "_notify_new_messages") as mock_notify:
                service._check_mailbox_sync(mb)
                mock_ssl.assert_called_once_with("imap.test.com", 993)
                mock_conn.login.assert_called_once_with("user", "pass")
                mock_conn.select.assert_called_once_with("INBOX")
                mock_notify.assert_called_once_with(mock_conn, mb, 3)

    def test_check_mailbox_sync_without_ssl(self):
        """Test _check_mailbox_sync without SSL connection."""
        from postoffice.service import PostofficeService, MailboxConfig

        mb = MailboxConfig(host="imap.test.com", username="user", password="pass", use_ssl=False, port=143)
        service = PostofficeService(config={"enabled": False, "poll_interval": 30, "mailboxes": []})

        mock_conn = MagicMock()
        mock_conn.search.return_value = ("OK", [b""])

        with patch("imaplib.IMAP4", return_value=mock_conn) as mock_imap:
            with patch.object(service, "_notify_new_messages") as mock_notify:
                service._check_mailbox_sync(mb)
                mock_imap.assert_called_once_with("imap.test.com", 143)
                mock_notify.assert_not_called()

    def test_check_mailbox_sync_handles_login_error(self):
        """Test _check_mailbox_sync handles login error."""
        from postoffice.service import PostofficeService, MailboxConfig

        mb = MailboxConfig(host="imap.test.com", username="user", password="wrong")
        service = PostofficeService(config={"enabled": False, "poll_interval": 30, "mailboxes": []})

        with patch("imaplib.IMAP4_SSL", side_effect=imaplib.IMAP4.error("Auth failed")):
            service._check_mailbox_sync(mb)

    def test_check_mailbox_sync_handles_connection_error(self):
        """Test _check_mailbox_sync handles connection error."""
        from postoffice.service import PostofficeService, MailboxConfig

        mb = MailboxConfig(host="imap.test.com", username="user", password="pass")
        service = PostofficeService(config={"enabled": False, "poll_interval": 30, "mailboxes": []})

        with patch("imaplib.IMAP4_SSL", side_effect=Exception("Connection refused")):
            service._check_mailbox_sync(mb)


@pytest.mark.integration
class TestNewEmailDetection(unittest.TestCase):
    """Test new email detection logic."""

    def test_notify_new_messages_fetches_envelopes(self):
        """Test _notify_new_messages fetches envelope for new messages."""
        from postoffice.service import PostofficeService, MailboxConfig

        mb = MailboxConfig(host="imap.test.com", username="user", password="pass")
        service = PostofficeService(config={"enabled": False, "poll_interval": 30, "mailboxes": []})

        mock_conn = MagicMock()
        mock_conn.search.return_value = ("OK", [b"1 2 3 4 5"])
        mock_conn.fetch.return_value = ("OK", [(b"1 (ENVELOPE (...)", b"ENVELOPE_DATA")])

        with patch.object(service, "_process_message_envelope") as mock_process:
            service._notify_new_messages(mock_conn, mb, 5)
            self.assertEqual(mock_process.call_count, 5)

    def test_notify_new_messages_limits_to_five(self):
        """Test _notify_new_messages limits to 5 messages."""
        from postoffice.service import PostofficeService, MailboxConfig

        mb = MailboxConfig(host="imap.test.com", username="user", password="pass")
        service = PostofficeService(config={"enabled": False, "poll_interval": 30, "mailboxes": []})

        mock_conn = MagicMock()
        mock_conn.search.return_value = ("OK", [b"1 2 3 4 5 6 7 8 9 10"])
        mock_conn.fetch.return_value = ("OK", [(b"1 (ENVELOPE (...)", b"ENVELOPE_DATA")])

        with patch.object(service, "_process_message_envelope") as mock_process:
            service._notify_new_messages(mock_conn, mb, 10)
            self.assertEqual(mock_process.call_count, 5)

    def test_notify_new_messages_handles_no_messages(self):
        """Test _notify_new_messages with no messages."""
        from postoffice.service import PostofficeService, MailboxConfig

        mb = MailboxConfig(host="imap.test.com", username="user", password="pass")
        service = PostofficeService(config={"enabled": False, "poll_interval": 30, "mailboxes": []})

        mock_conn = MagicMock()
        mock_conn.search.return_value = ("OK", [b""])

        with patch.object(service, "_process_message_envelope") as mock_process:
            service._notify_new_messages(mock_conn, mb, 0)
            mock_process.assert_not_called()


@pytest.mark.integration
class TestMessageEnvelopeProcessing(unittest.TestCase):
    """Test message envelope processing."""

    def test_process_message_envelope_basic(self):
        """Test basic envelope processing."""
        from postoffice.service import PostofficeService, MailboxConfig
        from email.parser import BytesParser
        from email.policy import default

        mb = MailboxConfig(host="imap.test.com", username="user", password="pass")
        service = PostofficeService(config={"enabled": False, "poll_interval": 30, "mailboxes": []})

        parser = BytesParser(policy=default)
        raw_msg = (
            "From: sender@example.com\r\n"
            "Subject: Test Subject\r\n"
            "\r\n"
            "This is the body."
        ).encode()
        msg = parser.parsebytes(raw_msg)
        envelope = msg.as_bytes()

        with patch("postoffice.service.message_send") as mock_send:
            service._process_message_envelope(envelope, mb)
            mock_send.assert_called_once()
            call_kwargs = mock_send.call_args.kwargs
            self.assertEqual(call_kwargs["sender_moniker"], "postoffice")
            self.assertEqual(call_kwargs["recipients"], ["@everyone"])
            self.assertIn("sender@example.com", call_kwargs["template"])
            self.assertIn("Test Subject", call_kwargs["template"])

    def test_process_message_envelope_multipart(self):
        """Test envelope processing with multipart message."""
        from postoffice.service import PostofficeService, MailboxConfig
        from email.parser import BytesParser
        from email.policy import default

        mb = MailboxConfig(host="imap.test.com", username="user", password="pass")
        service = PostofficeService(config={"enabled": False, "poll_interval": 30, "mailboxes": []})

        parser = BytesParser(policy=default)
        raw_msg = (
            "From: sender@example.com\r\n"
            "Subject: Multipart Test\r\n"
            "MIME-Version: 1.0\r\n"
            "Content-Type: multipart/alternative; boundary=boundary\r\n"
            "\r\n"
            "--boundary\r\n"
            "Content-Type: text/plain\r\n"
            "\r\n"
            "Plain text body."
            "\r\n--boundary\r\n"
            "Content-Type: text/html\r\n"
            "\r\n"
            "<html>HTML body</html>"
            "\r\n--boundary--"
        ).encode()
        msg = parser.parsebytes(raw_msg)
        envelope = msg.as_bytes()

        with patch("postoffice.service.message_send") as mock_send:
            service._process_message_envelope(envelope, mb)
            mock_send.assert_called_once()

    def test_process_message_envelope_body_preview(self):
        """Test body preview is limited to 500 chars."""
        from postoffice.service import PostofficeService, MailboxConfig
        from email.parser import BytesParser
        from email.policy import default

        mb = MailboxConfig(host="imap.test.com", username="user", password="pass")
        service = PostofficeService(config={"enabled": False, "poll_interval": 30, "mailboxes": []})

        long_body = "A" * 1000

        parser = BytesParser(policy=default)
        raw_msg = (
            "From: sender@example.com\r\n"
            "Subject: Long Body Test\r\n"
            "\r\n"
            + long_body
        ).encode()
        msg = parser.parsebytes(raw_msg)
        envelope = msg.as_bytes()

        with patch("postoffice.service.message_send") as mock_send:
            service._process_message_envelope(envelope, mb)
            call_kwargs = mock_send.call_args.kwargs
            self.assertLessEqual(len(call_kwargs["template"]), 600)


def run_tests():
    """Run all tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestIMAPConnection))
    suite.addTests(loader.loadTestsFromTestCase(TestNewEmailDetection))
    suite.addTests(loader.loadTestsFromTestCase(TestMessageEnvelopeProcessing))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
