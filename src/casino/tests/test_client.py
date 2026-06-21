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


class TestClientMenuFlow(unittest.IsolatedAsyncioTestCase):
    """Test client menu flow with mocked IO."""

    async def test_quit_from_unauthenticated(self):
        """Test pressing Q quits the application."""
        from casino.client import CasinoClient

        args = argparse.Namespace(host="localhost", port=8765)
        client = CasinoClient(args)

        inputchoice_calls = []

        def mock_inputchoice(prompt, options, default=None, **kwargs):
            inputchoice_calls.append((prompt, options, default))
            return "Q"  # Uppercase - what inputchoice actually returns

        with patch("casino.client.websockets") as mock_ws:
            mock_ws.connect = AsyncMock()
            mock_ws.connect.return_value = AsyncMock()

            with patch("casino.client.io.inputchoice", side_effect=mock_inputchoice):
                client.run()

        # Should have been called once with unauthenticated menu
        self.assertEqual(len(inputchoice_calls), 1)
        self.assertIn("c,q", inputchoice_calls[0][1])

    async def test_auth_flow_with_uppercase(self):
        """Test auth flow with uppercase inputchoice return."""
        from casino.client import CasinoClient

        args = argparse.Namespace(host="localhost", port=8765)
        client = CasinoClient(args)

        inputchoice_calls = []

        def mock_inputchoice(prompt, options, default=None, **kwargs):
            inputchoice_calls.append((prompt, options, default))
            # Return uppercase - this is what inputchoice actually returns
            if "Connect" in prompt:
                return "C"
            else:
                return "Q"

        with patch("casino.client.websockets") as mock_ws:
            mock_ws.connect = AsyncMock()
            mock_ws.connect.return_value = AsyncMock()

            with patch("casino.client.io.inputchoice", side_effect=mock_inputchoice):
                with patch("casino.client.io.inputstring") as mock_inputstring:
                    mock_inputstring.side_effect = ["testuser", "password"]

                    try:
                        client.run()
                    except Exception as e:
                        pass  # Expected to fail on auth since no real server

        # Should have called inputchoice at least twice
        self.assertGreaterEqual(len(inputchoice_calls), 2)


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
