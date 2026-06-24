#!/usr/bin/env python3
# casino/tests/test_postoffice_background_task.py
# Tests for postoffice background polling task

import asyncio
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, "/home/opencode/data/work/casino/src")


@pytest.mark.skip(reason="Deprecated - postoffice service moved to mistermcfeely package")
class TestPostofficeBackgroundTask(unittest.IsolatedAsyncioTestCase):
    """Test background polling task functionality."""

    async def test_poll_loop_runs_and_stops(self):
        """Test poll loop runs and can be stopped."""
        from casino.services.postoffice import PostofficeService

        service = PostofficeService(config={
            "enabled": True,
            "poll_interval": 1,
            "mailboxes": []
        })

        async def stop_after_short_delay():
            await asyncio.sleep(0.1)
            service.stop()

        task = asyncio.create_task(stop_after_short_delay())
        await service._poll_loop()
        await task

        self.assertFalse(service._running)

    async def test_poll_loop_catches_exceptions(self):
        """Test poll loop handles exceptions without crashing."""
        from casino.services.postoffice import PostofficeService

        call_count = 0

        async def failing_poll():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Test error")
            service._running = False

        service = PostofficeService(config={
            "enabled": True,
            "poll_interval": 1,
            "mailboxes": []
        })
        service._running = True

        with patch.object(service, "_poll_all_mailboxes", side_effect=failing_poll):
            await service._poll_loop()

        self.assertEqual(call_count, 3)

    async def test_poll_all_mailboxes_empty(self):
        """Test polling with no mailboxes configured."""
        from casino.services.postoffice import PostofficeService

        service = PostofficeService(config={
            "enabled": True,
            "poll_interval": 30,
            "mailboxes": []
        })

        await service._poll_all_mailboxes()

    async def test_poll_all_mailboxes_calls_check(self):
        """Test polling iterates through all mailboxes."""
        from casino.services.postoffice import PostofficeService, MailboxConfig

        mailboxes = [
            MailboxConfig(host="mail1.example.com", username="u1", password="p1"),
            MailboxConfig(host="mail2.example.com", username="u2", password="p2"),
        ]

        service = PostofficeService(config={
            "enabled": True,
            "poll_interval": 30,
            "mailboxes": [vars(mb) for mb in mailboxes]
        })

        with patch.object(service, "_check_mailbox", new_callable=AsyncMock) as mock_check:
            await service._poll_all_mailboxes()
            self.assertEqual(mock_check.call_count, 2)

    async def test_check_mailbox_runs_in_executor(self):
        """Test _check_mailbox runs sync IMAP in executor."""
        from casino.services.postoffice import PostofficeService, MailboxConfig

        mb = MailboxConfig(host="mail.example.com", username="user", password="pass")
        service = PostofficeService(config={
            "enabled": True,
            "poll_interval": 30,
            "mailboxes": [vars(mb)]
        })

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.run_in_executor = AsyncMock()
            await service._check_mailbox(mb)
            mock_loop.return_value.run_in_executor.assert_called_once()


@pytest.mark.skip(reason="Deprecated - postoffice service moved to mistermcfeely package")
class TestStartStopFunctions(unittest.IsolatedAsyncioTestCase):
    """Test start/stop module functions."""

    async def test_start_postoffice_service(self):
        """Test start_postoffice_service function."""
        from casino.services.postoffice import start_postoffice_service, get_postoffice_service, PostofficeService
        import casino.services.postoffice as postoffice_module

        postoffice_module._service_instance = None

        test_config = {"enabled": True, "poll_interval": 30, "mailboxes": []}
        service = get_postoffice_service(test_config)
        
        start_postoffice_service()
        self.assertIsNotNone(postoffice_module._service_instance)
        self.assertTrue(postoffice_module._service_instance.is_enabled)

        postoffice_module._service_instance.stop()
        postoffice_module._service_instance = None

    async def test_stop_postoffice_service(self):
        """Test stop_postoffice_service function."""
        from casino.services.postoffice import (
            start_postoffice_service,
            stop_postoffice_service,
            PostofficeService
        )
        import casino.services.postoffice as postoffice_module

        postoffice_module._service_instance = PostofficeService(config={
            "enabled": True,
            "poll_interval": 1,
            "mailboxes": []
        })
        postoffice_module._service_instance.start()

        stop_postoffice_service()
        self.assertIsNone(postoffice_module._service_instance)


@pytest.mark.skip(reason="Deprecated - postoffice service moved to mistermcfeely package")
class TestServiceLifecycle(unittest.IsolatedAsyncioTestCase):
    """Test service lifecycle scenarios."""

    async def test_service_restart(self):
        """Test service can be restarted after stopping."""
        from casino.services.postoffice import PostofficeService

        service = PostofficeService(config={
            "enabled": True,
            "poll_interval": 1,
            "mailboxes": []
        })

        service.start()
        self.assertTrue(service._running)
        task1 = service._task

        service.stop()
        self.assertFalse(service._running)

        service.start()
        self.assertTrue(service._running)
        self.assertIsNotNone(service._task)

        service.stop()

    async def test_multiple_services_independent(self):
        """Test multiple service instances are independent."""
        from casino.services.postoffice import PostofficeService

        service1 = PostofficeService(config={
            "enabled": True,
            "poll_interval": 1,
            "mailboxes": []
        })
        service2 = PostofficeService(config={
            "enabled": True,
            "poll_interval": 2,
            "mailboxes": []
        })

        service1.start()
        service2.start()

        self.assertTrue(service1._running)
        self.assertTrue(service2._running)
        self.assertEqual(service1.poll_interval, 1)
        self.assertEqual(service2.poll_interval, 2)

        service1.stop()
        service2.stop()


def run_tests():
    """Run all tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestPostofficeBackgroundTask))
    suite.addTests(loader.loadTestsFromTestCase(TestStartStopFunctions))
    suite.addTests(loader.loadTestsFromTestCase(TestServiceLifecycle))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
