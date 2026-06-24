#!/usr/bin/env python3
# casino/tests/test_postoffice_config.py
# Tests for postoffice configuration loading

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, "/home/opencode/data/work/casino/src")


class TestPostofficeConfig(unittest.TestCase):
    """Test postoffice configuration loading."""

    def setUp(self):
        self.env_vars_to_clean = [
            "CASINO_POSTOFFICE_ENABLED",
            "CASINO_POSTOFFICE_POLL_INTERVAL",
            "CASINO_DEBUG",
        ]
        for var in self.env_vars_to_clean:
            if var in os.environ:
                del os.environ[var]

    def tearDown(self):
        for var in self.env_vars_to_clean:
            if var in os.environ:
                del os.environ[var]

    def test_get_postoffice_config_default(self):
        """Test getting postoffice config with no defaults."""
        from casino.config import get_postoffice_config

        config = get_postoffice_config()
        self.assertEqual(config, {})

    def test_config_priority_env_overrides_file(self):
        """Test that env vars override config file."""
        os.environ["CASINO_POSTOFFICE_ENABLED"] = "true"
        os.environ["CASINO_POSTOFFICE_POLL_INTERVAL"] = "60"

        from casino.config import load_config, get_postoffice_config

        config = load_config()
        self.assertTrue(config["postoffice"]["enabled"])
        self.assertEqual(config["postoffice"]["poll_interval"], 60)

        postoffice_config = get_postoffice_config(config)
        self.assertTrue(postoffice_config["enabled"])
        self.assertEqual(postoffice_config["poll_interval"], 60)

    def test_config_priority_file_only(self):
        """Test that config file provides all values."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "postoffice": {
                    "enabled": True,
                    "poll_interval": 120,
                    "mailboxes": [
                        {"host": "mail.example.com", "username": "test", "password": "pass"}
                    ]
                }
            }, f)
            config_file = f.name

        try:
            from casino.config import load_config

            loaded_config = load_config(config_file=config_file)
            self.assertTrue(loaded_config["postoffice"]["enabled"])
            self.assertEqual(loaded_config["postoffice"]["poll_interval"], 120)
            self.assertEqual(len(loaded_config["postoffice"]["mailboxes"]), 1)
        finally:
            os.unlink(config_file)

    def test_config_priority_overrides_highest(self):
        """Test that overrides have highest priority."""
        os.environ["CASINO_POSTOFFICE_ENABLED"] = "true"
        os.environ["CASINO_POSTOFFICE_POLL_INTERVAL"] = "45"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "postoffice": {
                    "enabled": False,
                    "poll_interval": 90,
                }
            }, f)
            config_file = f.name

        try:
            from casino.config import load_config

            config = load_config(
                config_file=config_file,
                postoffice={"enabled": True, "poll_interval": 15}
            )
            self.assertTrue(config["postoffice"]["enabled"])
            self.assertEqual(config["postoffice"]["poll_interval"], 15)
        finally:
            os.unlink(config_file)

    def test_mailboxes_loaded_correctly(self):
        """Test that mailboxes are loaded from config."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "postoffice": {
                    "enabled": True,
                    "poll_interval": 30,
                    "mailboxes": [
                        {
                            "host": "imap.gmail.com",
                            "username": "user@gmail.com",
                            "password": "apppassword",
                            "mailbox": "INBOX",
                            "use_ssl": True,
                            "port": 993
                        },
                        {
                            "host": "imap.example.com",
                            "username": "other",
                            "password": "secret",
                            "mailbox": "Work",
                            "use_ssl": False,
                            "port": 143
                        }
                    ]
                }
            }, f)
            config_file = f.name

        try:
            from casino.config import load_config

            loaded_config = load_config(config_file=config_file)
            mailboxes = loaded_config["postoffice"]["mailboxes"]

            self.assertEqual(len(mailboxes), 2)
            self.assertEqual(mailboxes[0]["host"], "imap.gmail.com")
            self.assertEqual(mailboxes[0]["port"], 993)
            self.assertTrue(mailboxes[0]["use_ssl"])
            self.assertEqual(mailboxes[1]["host"], "imap.example.com")
            self.assertEqual(mailboxes[1]["port"], 143)
            self.assertFalse(mailboxes[1]["use_ssl"])
        finally:
            os.unlink(config_file)

    def test_env_var_boolean_parsing(self):
        """Test that env var booleans are parsed correctly."""
        os.environ["CASINO_POSTOFFICE_ENABLED"] = "True"
        from casino.config import load_config
        config = load_config()
        self.assertTrue(config["postoffice"]["enabled"])

        os.environ["CASINO_POSTOFFICE_ENABLED"] = "false"
        config = load_config()
        self.assertFalse(config["postoffice"]["enabled"])

    def test_env_var_integer_parsing(self):
        """Test that env var integers are parsed correctly."""
        os.environ["CASINO_POSTOFFICE_POLL_INTERVAL"] = "300"
        from casino.config import load_config
        config = load_config()
        self.assertEqual(config["postoffice"]["poll_interval"], 300)


class TestPostofficeServiceConfig(unittest.TestCase):
    """Test that PostofficeService uses config correctly."""

    def test_service_disabled_by_default(self):
        """Test service is disabled when enabled=false in config."""
        from casino.services.postoffice import PostofficeService

        service = PostofficeService(config={"enabled": False, "poll_interval": 30, "mailboxes": []})
        self.assertFalse(service.is_enabled)
        self.assertEqual(service.poll_interval, 30)

    def test_service_enabled_when_configured(self):
        """Test service is enabled when enabled=true in config."""
        from casino.services.postoffice import PostofficeService

        service = PostofficeService(config={"enabled": True, "poll_interval": 60, "mailboxes": []})
        self.assertTrue(service.is_enabled)
        self.assertEqual(service.poll_interval, 60)

    def test_mailboxes_loaded_from_config(self):
        """Test mailboxes are loaded from config into service."""
        from casino.services.postoffice import PostofficeService, MailboxConfig

        mailboxes = [
            {"host": "imap.test.com", "username": "user", "password": "pass", "use_ssl": True}
        ]
        service = PostofficeService(config={"enabled": True, "poll_interval": 30, "mailboxes": mailboxes})

        self.assertEqual(len(service._mailboxes), 1)
        self.assertIsInstance(service._mailboxes[0], MailboxConfig)
        self.assertEqual(service._mailboxes[0].host, "imap.test.com")


def run_tests():
    """Run all tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestPostofficeConfig))
    suite.addTests(loader.loadTestsFromTestCase(TestPostofficeServiceConfig))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
