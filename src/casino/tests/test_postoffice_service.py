#!/usr/bin/env python3
# casino/tests/test_postoffice_service.py
# Tests for PostofficeService class

import asyncio
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, "/home/opencode/data/work/mistermcfeely/src")
sys.path.insert(0, "/home/opencode/data/work/casino/src")


class TestMailboxConfig(unittest.TestCase):
    """Test MailboxConfig class."""

    def test_mailbox_config_defaults(self):
        """Test mailbox config default values."""
        from postoffice.service import MailboxConfig

        mb = MailboxConfig(host="imap.example.com", username="user", password="pass")
        self.assertEqual(mb.host, "imap.example.com")
        self.assertEqual(mb.username, "user")
        self.assertEqual(mb.password, "pass")
        self.assertEqual(mb.mailbox, "INBOX")
        self.assertTrue(mb.use_ssl)
        self.assertEqual(mb.port, 993)

    def test_mailbox_config_custom_values(self):
        """Test mailbox config with custom values."""
        from postoffice.service import MailboxConfig

        mb = MailboxConfig(
            host="mail.test.com",
            username="testuser",
            password="secret",
            mailbox="Work",
            use_ssl=False,
            port=143
        )
        self.assertEqual(mb.host, "mail.test.com")
        self.assertEqual(mb.mailbox, "Work")
        self.assertFalse(mb.use_ssl)
        self.assertEqual(mb.port, 143)


class TestPostofficeService(unittest.IsolatedAsyncioTestCase):
    """Test PostofficeService class."""

    def test_service_initialization_disabled(self):
        """Test service initializes correctly when disabled."""
        from postoffice.service import PostofficeService

        service = PostofficeService(config={
            "enabled": False,
            "poll_interval": 30,
            "mailboxes": []
        })
        self.assertFalse(service.is_enabled)
        self.assertEqual(service.poll_interval, 30)
        self.assertFalse(service._running)
        self.assertIsNone(service._task)

    def test_service_initialization_enabled(self):
        """Test service initializes correctly when enabled."""
        from postoffice.service import PostofficeService

        service = PostofficeService(config={
            "enabled": True,
            "poll_interval": 60,
            "mailboxes": [
                {"host": "imap.test.com", "username": "user", "password": "pass"}
            ]
        })
        self.assertTrue(service.is_enabled)
        self.assertEqual(service.poll_interval, 60)
        self.assertEqual(len(service._mailboxes), 1)

    def test_service_loads_mailboxes(self):
        """Test service loads mailbox configurations."""
        from postoffice.service import PostofficeService, MailboxConfig

        mailboxes = [
            {"host": "imap.gmail.com", "username": "user", "password": "pass", "use_ssl": True},
            {"host": "imap.work.com", "username": "worker", "password": "secret", "use_ssl": True, "port": 993}
        ]
        service = PostofficeService(config={
            "enabled": True,
            "poll_interval": 30,
            "mailboxes": mailboxes
        })
        self.assertEqual(len(service._mailboxes), 2)
        self.assertIsInstance(service._mailboxes[0], MailboxConfig)
        self.assertEqual(service._mailboxes[0].host, "imap.gmail.com")
        self.assertEqual(service._mailboxes[1].host, "imap.work.com")

    def test_service_handles_invalid_mailbox_config(self):
        """Test service handles invalid mailbox config gracefully."""
        from postoffice.service import PostofficeService

        mailboxes = [
            {"host": "valid.com", "username": "user", "password": "pass"},
            {"host": "", "username": "", "password": ""},  # Invalid - empty values
        ]
        service = PostofficeService(config={
            "enabled": True,
            "poll_interval": 30,
            "mailboxes": mailboxes
        })
        self.assertEqual(len(service._mailboxes), 2)


class TestPostofficeServiceStartStop(unittest.IsolatedAsyncioTestCase):
    """Test service start/stop functionality."""

    async def test_start_disabled_service(self):
        """Test starting a disabled service does nothing."""
        from postoffice.service import PostofficeService

        service = PostofficeService(config={
            "enabled": False,
            "poll_interval": 30,
            "mailboxes": []
        })
        service.start()
        self.assertFalse(service._running)
        self.assertIsNone(service._task)

    async def test_start_enabled_service(self):
        """Test starting an enabled service creates background task."""
        from postoffice.service import PostofficeService

        service = PostofficeService(config={
            "enabled": True,
            "poll_interval": 1,
            "mailboxes": []
        })
        service.start()
        self.assertTrue(service._running)
        self.assertIsNotNone(service._task)
        service.stop()

    async def test_start_already_running_service(self):
        """Test starting an already running service logs warning."""
        from postoffice.service import PostofficeService

        service = PostofficeService(config={
            "enabled": True,
            "poll_interval": 1,
            "mailboxes": []
        })
        service.start()
        self.assertTrue(service._running)
        service.start()  # Should log warning
        service.stop()

    async def test_stop_service(self):
        """Test stopping a running service."""
        from postoffice.service import PostofficeService

        service = PostofficeService(config={
            "enabled": True,
            "poll_interval": 1,
            "mailboxes": []
        })
        service.start()
        self.assertTrue(service._running)
        service.stop()
        self.assertFalse(service._running)
        self.assertIsNone(service._task)

    async def test_stop_not_running_service(self):
        """Test stopping a non-running service does nothing."""
        from postoffice.service import PostofficeService

        service = PostofficeService(config={
            "enabled": False,
            "poll_interval": 30,
            "mailboxes": []
        })
        service.stop()
        self.assertFalse(service._running)


class TestPostofficeSingleton(unittest.IsolatedAsyncioTestCase):
    """Test singleton pattern for postoffice service."""

    async def test_get_postoffice_service_singleton(self):
        """Test get_postoffice_service returns singleton."""
        from postoffice.service import get_postoffice_service, PostofficeService
        import postoffice.service as postoffice_module

        postoffice_module._service_instance = None

        service1 = get_postoffice_service(config={"enabled": False, "poll_interval": 30, "mailboxes": []})
        service2 = get_postoffice_service(config={"enabled": False, "poll_interval": 30, "mailboxes": []})

        self.assertIs(service1, service2)


def run_tests():
    """Run all tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestMailboxConfig))
    suite.addTests(loader.loadTestsFromTestCase(TestPostofficeService))
    suite.addTests(loader.loadTestsFromTestCase(TestPostofficeServiceStartStop))
    suite.addTests(loader.loadTestsFromTestCase(TestPostofficeSingleton))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
