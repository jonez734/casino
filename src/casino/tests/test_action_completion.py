#!/usr/bin/env python3
# casino/tests/test_action_completion.py
# Tests for ActionInputHandler tab completion

import sys
import unittest

sys.path.insert(0, "/home/opencode/data/work/casino/src")


class TestActionInputHandler(unittest.TestCase):
    """Test ActionInputHandler tab completion functionality."""

    def setUp(self):
        """Set up test fixtures."""
        from casino.connect import ActionInputHandler

        self.actions = [
            {"action": "bet", "label": "Bet", "hotkey": "b"},
            {"action": "hit", "label": "Hit", "hotkey": "h"},
            {"action": "stand", "label": "Stand", "hotkey": "s"},
            {"action": "double_down", "label": "Double Down", "hotkey": "d"},
            {"action": "split", "label": "Split", "hotkey": "p"},
        ]
        self.handler = ActionInputHandler(self.actions)

    def test_get_matches_empty_prefix_returns_all(self):
        """Test that empty prefix returns all actions."""
        matches = self.handler.get_matches("")
        self.assertEqual(len(matches), 5)
        self.assertIn("bet", matches)
        self.assertIn("hit", matches)
        self.assertIn("stand", matches)
        self.assertIn("double_down", matches)
        self.assertIn("split", matches)

    def test_get_matches_exact_action_name(self):
        """Test matching exact action name."""
        matches = self.handler.get_matches("bet")
        self.assertEqual(matches, ["bet"])

    def test_get_matches_partial_action_name(self):
        """Test matching partial action name."""
        matches = self.handler.get_matches("s")
        self.assertIn("stand", matches)

    def test_get_matches_hotkey(self):
        """Test matching by hotkey."""
        matches = self.handler.get_matches("b")
        self.assertIn("bet", matches)

    def test_get_matches_case_insensitive(self):
        """Test case-insensitive matching."""
        matches = self.handler.get_matches("HIT")
        self.assertIn("hit", matches)

    def test_get_matches_no_match(self):
        """Test no matches for unknown prefix."""
        matches = self.handler.get_matches("xyz")
        self.assertEqual(matches, [])

    def test_get_matches_partial_double(self):
        """Test partial match on double_down."""
        matches = self.handler.get_matches("dou")
        self.assertIn("double_down", matches)

    def test_get_matches_sorted(self):
        """Test that matches are sorted."""
        matches = self.handler.get_matches("d")
        self.assertEqual(matches, sorted(matches))

    def test_resolve_exact_action(self):
        """Test resolving exact action name."""
        result = self.handler.resolve("bet")
        self.assertEqual(result, "bet")

    def test_resolve_hotkey(self):
        """Test resolving by hotkey."""
        result = self.handler.resolve("b")
        self.assertEqual(result, "bet")

    def test_resolve_case_insensitive(self):
        """Test case-insensitive resolution."""
        result = self.handler.resolve("HIT")
        self.assertEqual(result, "hit")

    def test_resolve_partial_match(self):
        """Test resolving partial action name."""
        result = self.handler.resolve("s")
        self.assertEqual(result, "stand")

    def test_resolve_no_match(self):
        """Test resolving unknown action returns None."""
        result = self.handler.resolve("xyz")
        self.assertIsNone(result)

    def test_resolve_empty_returns_none(self):
        """Test resolving empty string returns None."""
        result = self.handler.resolve("")
        self.assertIsNone(result)

    def test_get_completer_returns_self(self):
        """Test get_completer returns self for inputstring."""
        completer = self.handler.get_completer()
        self.assertIs(completer, self.handler)

    def test_action_map_populated(self):
        """Test that action_map is correctly populated."""
        self.assertEqual(self.handler.action_map["bet"], "bet")
        self.assertEqual(self.handler.action_map["b"], "bet")
        self.assertEqual(self.handler.action_map["hit"], "hit")
        self.assertEqual(self.handler.action_map["h"], "hit")

    def test_multiple_actions_starting_same_letter(self):
        """Test actions with same starting letter."""
        from casino.connect import ActionInputHandler
        actions = [
            {"action": "check", "label": "Check", "hotkey": "c"},
            {"action": "call", "label": "Call", "hotkey": "c"},
            {"action": "fold", "label": "Fold", "hotkey": "f"},
        ]
        handler = ActionInputHandler(actions)
        matches = handler.get_matches("c")
        self.assertIn("check", matches)
        self.assertIn("call", matches)


class TestResolveAction(unittest.TestCase):
    """Test standalone resolve_action function."""

    def test_resolve_action_exact_match(self):
        """Test exact action name match."""
        from casino.connect import resolve_action

        actions = [{"action": "bet", "label": "Bet", "hotkey": "b"}]
        result = resolve_action("bet", actions)
        self.assertEqual(result, "bet")

    def test_resolve_action_hotkey_match(self):
        """Test hotkey match."""
        from casino.connect import resolve_action

        actions = [{"action": "bet", "label": "Bet", "hotkey": "b"}]
        result = resolve_action("b", actions)
        self.assertEqual(result, "bet")

    def test_resolve_action_ambiguous(self):
        """Test ambiguous match raises ValueError."""
        from casino.connect import resolve_action

        actions = [
            {"action": "check", "label": "Check", "hotkey": "k"},
            {"action": "call", "label": "Call", "hotkey": "l"},
        ]
        with self.assertRaises(ValueError) as ctx:
            resolve_action("c", actions)
        self.assertIn("Which actions?", str(ctx.exception))


class TestCompleterInterface(unittest.TestCase):
    """Test that ActionInputHandler implements Completer interface."""

    def test_is_callable(self):
        """Test that handler is callable for inputstring."""
        from casino.connect import ActionInputHandler

        actions = [{"action": "bet", "label": "Bet", "hotkey": "b"}]
        handler = ActionInputHandler(actions)
        self.assertTrue(callable(handler))

    def test_accepts_buffer_and_kwargs(self):
        """Test that handler accepts buffer and kwargs like Completer."""
        from casino.connect import ActionInputHandler

        actions = [{"action": "bet", "label": "Bet", "hotkey": "b"}]
        handler = ActionInputHandler(actions)
        result = handler("be", curpos=2)
        self.assertIsInstance(result, list)


def run_tests():
    """Run all tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestActionInputHandler))
    suite.addTests(loader.loadTestsFromTestCase(TestResolveAction))
    suite.addTests(loader.loadTestsFromTestCase(TestCompleterInterface))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
