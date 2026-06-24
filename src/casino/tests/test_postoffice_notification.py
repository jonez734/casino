#!/usr/bin/env python3
# casino/tests/test_postoffice_notification.py
# Tests for notification sending

import pytest
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, "/home/opencode/data/work/casino/src")


@pytest.mark.integration
class TestNotificationContent(unittest.TestCase):
    """Test notification content formatting."""

    def test_notification_includes_sender(self):
        """Test notification includes sender address."""
        from postoffice.service import PostofficeService, MailboxConfig
        from email.parser import BytesParser
        from email.policy import default

        mb = MailboxConfig(host="imap.test.com", username="user", password="pass")
        service = PostofficeService(config={"enabled": False, "poll_interval": 30, "mailboxes": []})

        parser = BytesParser(policy=default)
        raw_msg = b"From: John Doe <john@example.com>\r\nSubject: Hello\r\n\r\nTest message body."
        msg = parser.parsebytes(raw_msg)
        envelope = msg.as_bytes()

        with patch("bbsengine6.message_delivery.lib._validate_type_name", return_value=True):
            with patch("postoffice.service.message_send") as mock_send:
                service._process_message_envelope(envelope, mb)
                call_kwargs = mock_send.call_args.kwargs
                self.assertIn("john@example.com", call_kwargs["template"])
                self.assertIn("John Doe", call_kwargs["template"])

    def test_notification_includes_subject(self):
        """Test notification includes subject."""
        from postoffice.service import PostofficeService, MailboxConfig
        from email.parser import BytesParser
        from email.policy import default

        mb = MailboxConfig(host="imap.test.com", username="user", password="pass")
        service = PostofficeService(config={"enabled": False, "poll_interval": 30, "mailboxes": []})

        parser = BytesParser(policy=default)
        raw_msg = b"From: sender@example.com\r\nSubject: Important Message\r\n\r\nBody content here."
        msg = parser.parsebytes(raw_msg)
        envelope = msg.as_bytes()

        with patch("bbsengine6.message_delivery.lib._validate_type_name", return_value=True):
            with patch("postoffice.service.message_send") as mock_send:
                service._process_message_envelope(envelope, mb)
                call_kwargs = mock_send.call_args.kwargs
                self.assertIn("Important Message", call_kwargs["template"])

    def test_notification_includes_body_preview(self):
        """Test notification includes body preview."""
        from postoffice.service import PostofficeService, MailboxConfig
        from email.parser import BytesParser
        from email.policy import default

        mb = MailboxConfig(host="imap.test.com", username="user", password="pass")
        service = PostofficeService(config={"enabled": False, "poll_interval": 30, "mailboxes": []})

        parser = BytesParser(policy=default)
        raw_msg = b"From: sender@example.com\r\nSubject: Test\r\n\r\nThis is the preview text."
        msg = parser.parsebytes(raw_msg)
        envelope = msg.as_bytes()

        with patch("bbsengine6.message_delivery.lib._validate_type_name", return_value=True):
            with patch("postoffice.service.message_send") as mock_send:
                service._process_message_envelope(envelope, mb)
                call_kwargs = mock_send.call_args.kwargs
                self.assertIn("This is the preview text.", call_kwargs["template"])

    def test_notification_sender_moniker(self):
        """Test notification uses postoffice as sender moniker."""
        from postoffice.service import PostofficeService, MailboxConfig
        from email.parser import BytesParser
        from email.policy import default

        mb = MailboxConfig(host="imap.test.com", username="user", password="pass")
        service = PostofficeService(config={"enabled": False, "poll_interval": 30, "mailboxes": []})

        parser = BytesParser(policy=default)
        raw_msg = b"From: sender@example.com\r\nSubject: Test\r\n\r\nBody."
        msg = parser.parsebytes(raw_msg)
        envelope = msg.as_bytes()

        with patch("bbsengine6.message_delivery.lib._validate_type_name", return_value=True):
            with patch("postoffice.service.message_send") as mock_send:
                service._process_message_envelope(envelope, mb)
                call_kwargs = mock_send.call_args.kwargs
                self.assertEqual(call_kwargs["sender_moniker"], "postoffice")

    def test_notification_recipient_is_everyone(self):
        """Test notification sends to @everyone."""
        from postoffice.service import PostofficeService, MailboxConfig
        from email.parser import BytesParser
        from email.policy import default

        mb = MailboxConfig(host="imap.test.com", username="user", password="pass")
        service = PostofficeService(config={"enabled": False, "poll_interval": 30, "mailboxes": []})

        parser = BytesParser(policy=default)
        raw_msg = b"From: sender@example.com\r\nSubject: Test\r\n\r\nBody."
        msg = parser.parsebytes(raw_msg)
        envelope = msg.as_bytes()

        with patch("bbsengine6.message_delivery.lib._validate_type_name", return_value=True):
            with patch("postoffice.service.message_send") as mock_send:
                service._process_message_envelope(envelope, mb)
                call_kwargs = mock_send.call_args.kwargs
                self.assertEqual(call_kwargs["recipients"], ["@everyone"])

    def test_notification_message_type(self):
        """Test notification uses postoffice.email message type."""
        from postoffice.service import PostofficeService, MailboxConfig
        from email.parser import BytesParser
        from email.policy import default

        mb = MailboxConfig(host="imap.test.com", username="user", password="pass")
        service = PostofficeService(config={"enabled": False, "poll_interval": 30, "mailboxes": []})

        parser = BytesParser(policy=default)
        raw_msg = b"From: sender@example.com\r\nSubject: Test\r\n\r\nBody."
        msg = parser.parsebytes(raw_msg)
        envelope = msg.as_bytes()

        with patch("bbsengine6.message_delivery.lib._validate_type_name", return_value=True):
            with patch("postoffice.service.message_send") as mock_send:
                service._process_message_envelope(envelope, mb)
                call_kwargs = mock_send.call_args.kwargs
                self.assertEqual(call_kwargs["notification_type"], "postoffice.email")

    def test_notification_format(self):
        """Test notification format includes all parts."""
        from postoffice.service import PostofficeService, MailboxConfig
        from email.parser import BytesParser
        from email.policy import default

        mb = MailboxConfig(host="imap.test.com", username="user", password="pass")
        service = PostofficeService(config={"enabled": False, "poll_interval": 30, "mailboxes": []})

        parser = BytesParser(policy=default)
        raw_msg = b"From: test@sender.com\r\nSubject: Newsletter\r\n\r\nThis is the email content."
        msg = parser.parsebytes(raw_msg)
        envelope = msg.as_bytes()

        with patch("bbsengine6.message_delivery.lib._validate_type_name", return_value=True):
            with patch("postoffice.service.message_send") as mock_send:
                service._process_message_envelope(envelope, mb)
                call_kwargs = mock_send.call_args.kwargs
                content = call_kwargs["template"]
                self.assertTrue(content.startswith("From:"))
                self.assertIn("Subject:", content)
                self.assertIn("This is the email content.", content)


@pytest.mark.integration
class TestNotificationErrors(unittest.TestCase):
    """Test notification error handling."""

    def test_handles_missing_from_header(self):
        """Test handling of missing From header."""
        from postoffice.service import PostofficeService, MailboxConfig
        from email.parser import BytesParser
        from email.policy import default

        mb = MailboxConfig(host="imap.test.com", username="user", password="pass")
        service = PostofficeService(config={"enabled": False, "poll_interval": 30, "mailboxes": []})

        parser = BytesParser(policy=default)
        raw_msg = b"Subject: No From Header\r\n\r\nBody."
        msg = parser.parsebytes(raw_msg)
        envelope = msg.as_bytes()

        with patch("bbsengine6.message_delivery.lib._validate_type_name", return_value=True):
            with patch("postoffice.service.message_send") as mock_send:
                service._process_message_envelope(envelope, mb)
                call_kwargs = mock_send.call_args.kwargs
                self.assertIn("Unknown", call_kwargs["template"])

    def test_handles_missing_subject(self):
        """Test handling of missing Subject header."""
        from postoffice.service import PostofficeService, MailboxConfig
        from email.parser import BytesParser
        from email.policy import default

        mb = MailboxConfig(host="imap.test.com", username="user", password="pass")
        service = PostofficeService(config={"enabled": False, "poll_interval": 30, "mailboxes": []})

        parser = BytesParser(policy=default)
        raw_msg = b"From: sender@example.com\r\n\r\nBody."
        msg = parser.parsebytes(raw_msg)
        envelope = msg.as_bytes()

        with patch("bbsengine6.message_delivery.lib._validate_type_name", return_value=True):
            with patch("postoffice.service.message_send") as mock_send:
                service._process_message_envelope(envelope, mb)
                call_kwargs = mock_send.call_args.kwargs
                self.assertIn("No Subject", call_kwargs["template"])


def run_tests():
    """Run all tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestNotificationContent))
    suite.addTests(loader.loadTestsFromTestCase(TestNotificationErrors))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
