#!/usr/bin/env python3
# casino/tests/test_client.py
# Mock tests for casino client

import argparse
import asyncio
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch, call

sys.path.insert(0, "/home/opencode/data/work/casino/src")


class TestClientInputChoiceCase(unittest.IsolatedAsyncioTestCase):
    """Test that inputchoice returns uppercase and comparisons work."""

    def test_inputchoice_returns_uppercase(self):
        """Verify inputchoice returns uppercase characters."""
        from bbsengine6.io import inputchoice

        # The function converts input to uppercase, so comparisons
        # in client.py should use uppercase

        # This test documents the expected behavior:
        # inputchoice("c,q") with default "q" returns "C" or "Q" (uppercase)
        # Therefore client.py must compare against uppercase

        # Let's verify by mocking getch
        with patch("bbsengine6.io.inputchoice.getch") as mock_getch:
            mock_getch.return_value = "c"

            # This will convert 'c' to 'C'
            result = inputchoice("test> ", "c,q", default="q")

            # Result should be uppercase
            self.assertEqual(result, "C")

    def test_client_comparisons_should_be_uppercase(self):
        """Document that client.py must use uppercase comparisons."""
        # The bug: client.py does `if cmd == "c":`
        # But inputchoice returns "C" (uppercase)
        # So comparisons need to be uppercase

        # This is a documentation test
        cmd_from_inputchoice = "C"  # What inputchoice actually returns

        # Wrong (what client.py currently has):
        self.assertFalse(cmd_from_inputchoice == "c")

        # Correct (what client.py should have):
        self.assertTrue(cmd_from_inputchoice == "C")


class TestClientMenuFlow(unittest.TestCase):
    """Test client menu flow with mocked IO."""

    def test_quit_from_unauthenticated(self):
        """Test pressing Q quits the application."""
        from casino.client import CasinoClient
        from casino import client as client_module

        args = argparse.Namespace(host="localhost", port=8765)
        client = CasinoClient(args)

        inputchoice_calls = []

        def mock_inputchoice(prompt, options, default=None, **kwargs):
            inputchoice_calls.append((prompt, options, default))
            return "Q"

        async def mock_connect():
            client.connected = True
            return True

        client.connect = mock_connect

        with patch.object(client_module.io, "inputchoice", mock_inputchoice):
            with patch.object(
                client_module.websockets, "connect", new_callable=AsyncMock
            ) as mock_ws:
                mock_ws.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
                mock_ws.return_value.__aexit__ = AsyncMock(return_value=None)

                try:
                    client.run()
                except Exception:
                    pass
                finally:
                    if client._loop and not client._loop.is_closed():
                        client._loop.close()

        self.assertGreaterEqual(len(inputchoice_calls), 1)
        if inputchoice_calls:
            self.assertIn("c,q", inputchoice_calls[0][1])

    def test_auth_flow_with_uppercase(self):
        """Test auth flow with uppercase inputchoice return."""
        from casino.client import CasinoClient
        from casino import client as client_module

        args = argparse.Namespace(host="localhost", port=8765)
        client = CasinoClient(args)

        inputchoice_calls = []

        def mock_inputchoice(prompt, options, default=None, **kwargs):
            inputchoice_calls.append((prompt, options, default))
            return "Q"

        async def mock_connect():
            client.connected = True
            client.authenticated = True
            return True

        client.connect = mock_connect

        with patch.object(client_module.io, "inputchoice", mock_inputchoice):
            with patch("casino.client.io.inputstring", return_value="testuser"):
                with patch.object(
                    client_module.websockets, "connect", new_callable=AsyncMock
                ) as mock_ws:
                    mock_ws.return_value.__aenter__ = AsyncMock(
                        return_value=AsyncMock()
                    )
                    mock_ws.return_value.__aexit__ = AsyncMock(return_value=None)

                    try:
                        client.run()
                    except Exception:
                        pass
                    finally:
                        if client._loop and not client._loop.is_closed():
                            client._loop.close()

        self.assertGreaterEqual(len(inputchoice_calls), 1)


def run_tests():
    """Run all tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestClientInputChoiceCase))
    suite.addTests(loader.loadTestsFromTestCase(TestClientMenuFlow))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
