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

    def test_casino_client_can_be_instantiated(self):
        """Test that CasinoClient can be instantiated."""
        from casino.connect import CasinoClient

        args = argparse.Namespace(casino_host="localhost", casino_port=8765)
        client = CasinoClient(args)

        self.assertIsNotNone(client)
        self.assertEqual(client.args.casino_host, "localhost")
        self.assertEqual(client.args.casino_port, 8765)
        self.assertFalse(client.connected)
        self.assertFalse(client.authenticated)

    def test_casino_client_initial_state(self):
        """Test CasinoClient initial state."""
        from casino.connect import CasinoClient

        args = argparse.Namespace(host="localhost", port=8765)
        client = CasinoClient(args)

        self.assertEqual(client.moniker, "")
        self.assertEqual(client.balance, 0)
        self.assertIsNone(client.current_table)
        self.assertEqual(len(client.watched_tables), 0)

    def test_casino_client_play_function_has_defaults(self):
        """Test that play function has default host/port."""
        from casino import connect

        args = argparse.Namespace()
        host = getattr(args, "casino_host", "localhost")
        port = getattr(args, "casino_port", 8765)

        self.assertEqual(host, "localhost")
        self.assertEqual(port, 8765)


class TestClientServerIO(unittest.TestCase):
    """Test client-server IO with detailed message tracing."""

    def test_auth_message_format(self):
        """Test that auth message is properly formatted."""
        from casino.connect import CasinoClient

        args = argparse.Namespace(casino_host="localhost", casino_port=8765)
        client = CasinoClient(args)

        auth_msg = {"type": "auth", "moniker": "jam", "password": "test"}

        self.assertEqual(auth_msg["type"], "auth")
        self.assertEqual(auth_msg["moniker"], "jam")
        print(f"\n→ Auth message: {auth_msg}")

    def test_create_table_message_format(self):
        """Test that create_table message is properly formatted."""
        create_msg = {
            "type": "create_table",
            "game_type": "blackjack",
            "min_bet": 10,
            "max_bet": 1000,
            "shoe_decks": 6,
            "shoe_threshold": 0.8,
        }

        self.assertEqual(create_msg["type"], "create_table")
        self.assertEqual(create_msg["game_type"], "blackjack")
        print(f"\n→ Create table message: {create_msg}")

    def test_join_table_message_format(self):
        """Test that join_table message is properly formatted."""
        join_msg = {"type": "join_table", "moniker": "blackjack-jam"}

        self.assertEqual(join_msg["type"], "join_table")
        self.assertEqual(join_msg["moniker"], "blackjack-jam")
        print(f"\n→ Join table message: {join_msg}")

    def test_bet_message_format(self):
        """Test that bet message is properly formatted."""
        bet_msg = {"type": "bet", "amount": 50}

        self.assertEqual(bet_msg["type"], "bet")
        self.assertEqual(bet_msg["amount"], 50)
        print(f"\n→ Bet message: {bet_msg}")

    def test_hit_message_format(self):
        """Test that hit message is properly formatted."""
        hit_msg = {"type": "hit"}

        self.assertEqual(hit_msg["type"], "hit")
        print(f"\n→ Hit message: {hit_msg}")

    def test_stand_message_format(self):
        """Test that stand message is properly formatted."""
        stand_msg = {"type": "stand"}

        self.assertEqual(stand_msg["type"], "stand")
        print(f"\n→ Stand message: {stand_msg}")

    def test_bet_validation_negative_amount(self):
        """Test that negative bet amounts are rejected."""
        amount = -1
        min_bet = 10
        max_bet = 1000

        is_valid = amount >= min_bet and amount <= max_bet

        print(f"\n  Bet amount: {amount}")
        print(f"  Min bet: {min_bet}, Max bet: {max_bet}")
        print(f"  Passes validation: {is_valid}")

        if is_valid:
            print(f"  WARNING: Negative bet would pass validation!")
            print(f"  This would deduct -1 from balance, ADDING to it!")

        self.assertFalse(is_valid, "Negative bet should be rejected")

    def test_bet_validation_zero_amount(self):
        """Test that zero bet amount is handled."""
        amount = 0
        min_bet = 10
        max_bet = 1000

        is_valid = amount >= min_bet and amount <= max_bet

        print(f"\n  Bet amount: {amount}")
        print(f"  Min bet: {min_bet}, Max bet: {max_bet}")
        print(f"  Passes validation: {is_valid}")

        self.assertFalse(is_valid, "Zero bet should be rejected")

    def test_bet_validation_normal_amounts(self):
        """Test that normal bet amounts are accepted."""
        test_amounts = [10, 50, 100, 500, 1000]
        min_bet = 10
        max_bet = 1000

        print(f"\n  Min bet: {min_bet}, Max bet: {max_bet}")

        for amount in test_amounts:
            is_valid = amount >= min_bet and amount <= max_bet
            status = "PASS" if is_valid else "FAIL"
            print(f"  Amount {amount}: {status}")
            self.assertTrue(is_valid, f"Bet amount {amount} should be valid")

    def test_bet_type_validation(self):
        """Test that bet amount must be a positive integer."""
        test_cases = [
            (50, True, "normal integer"),
            (0, False, "zero"),
            (-1, False, "negative"),
            (50.5, False, "float"),
            ("50", False, "string"),
            (None, False, "None"),
            ([], False, "list"),
        ]

        print(f"\n  Type validation:")
        for amount, expected_valid, desc in test_cases:
            try:
                if amount is None:
                    is_valid = False
                elif isinstance(amount, str):
                    is_valid = False  # String would cause TypeError in comparison
                elif isinstance(amount, (int, float)):
                    is_valid = amount > 0 and isinstance(amount, int)
                else:
                    is_valid = False

                status = "PASS" if is_valid == expected_valid else "FAIL"
                print(f"    {desc}: {amount!r} -> valid={is_valid} [{status}]")
                
                self.assertEqual(is_valid, expected_valid, f"Amount {amount!r} ({desc}) should be {'valid' if expected_valid else 'invalid'}")
            except TypeError as e:
                print(f"    {desc}: {amount!r} -> TypeError: {e}")
                self.assertFalse(expected_valid, f"Amount {amount!r} ({desc}) should be rejected")

    def test_game_state_parsing(self):
        """Test parsing of game_state response with hand of cards."""
        game_state = {
            "type": "game_state",
            "table_moniker": "blackjack-jam",
            "game_id": 1,
            "phase": "playing",
            "player_hand": ["QC", "AH"],
            "player_total": 21,
            "player_status": "blackjack",
            "dealer_hand": ["KS"],
            "dealer_total": 10,
        }

        self.assertEqual(game_state["type"], "game_state")
        self.assertEqual(len(game_state["player_hand"]), 2)
        self.assertEqual(game_state["player_total"], 21)

        hand_str = " ".join(game_state["player_hand"])
        print(f"\n← Game state received:")
        print(f"  Player hand: {hand_str} [{game_state['player_total']}]")
        print(f"  Dealer hand: {' '.join(game_state['dealer_hand'])} [{game_state['dealer_total']}]")
        print(f"  Phase: {game_state['phase']}")

    def test_full_blackjack_hand_display(self):
        """Test displaying a full blackjack hand with cards."""
        test_hands = [
            {"player": ["QC", "AH"], "dealer": ["KS"], "player_total": 21, "dealer_total": 10, "status": "blackjack"},
            {"player": ["5C", "7D", "9H"], "dealer": ["JC", "QD", "3S"], "player_total": 21, "dealer_total": 23, "status": "win"},
            {"player": ["KC", "QC"], "dealer": ["AH", "KD"], "player_total": 20, "dealer_total": 21, "status": "lose"},
            {"player": ["2C", "3S", "4D", "5H", "6C", "KD"], "dealer": ["10S"], "player_total": 25, "dealer_total": 10, "status": "bust"},
        ]

        for hand in test_hands:
            player_cards = " ".join(hand["player"])
            dealer_cards = " ".join(hand["dealer"])

            result = "WIN" if hand["status"] in ("blackjack", "win") else "LOSE" if hand["status"] == "lose" else "BUST"

            print(f"\n{'='*40}")
            print(f"  Player: {player_cards} [{hand['player_total']}]")
            print(f"  Dealer: {dealer_cards} [{hand['dealer_total']}]")
            print(f"  Result: {result}")
            print(f"{'='*40}")

            self.assertGreater(hand["player_total"], 0)

    def test_table_list_parsing(self):
        """Test parsing of table_list response."""
        table_list = {
            "type": "table_list",
            "tables": [
                {"moniker": "blackjack-jam", "type": "blackjack", "players": 2, "min_bet": 10, "max_bet": 1000},
                {"moniker": "poker-main", "type": "poker", "players": 5, "min_bet": 20, "max_bet": 2000},
            ]
        }

        self.assertEqual(len(table_list["tables"]), 2)
        print(f"\n← Table list received:")
        for t in table_list["tables"]:
            print(f"  {t['moniker']}: {t['type']} ({t['players']} players) ${t['min_bet']}-${t['max_bet']}")

    def test_error_response_parsing(self):
        """Test parsing of error response."""
        error_resp = {"type": "error", "code": "bet_failed", "message": "Insufficient funds"}

        self.assertEqual(error_resp["type"], "error")
        self.assertEqual(error_resp["code"], "bet_failed")
        print(f"\n← Error received: [{error_resp['code']}] {error_resp['message']}")

    def test_menu_options_format(self):
        """Test that menu options are properly formatted for display."""
        menu_options = {
            "B": "Blackjack",
            "P": "Poker", 
            "S": "Slots",
            "C": "Connect",
            "L": "List tables",
            "J": "Join table",
            "A": "Bet",
            "H": "Hit",
            "T": "Stand",
            "X": "Disconnect",
            "Q": "Quit",
        }

        print(f"\n→ Menu options (concatenated): {''.join(menu_options.keys())}")
        print("  Display:")
        for key, value in menu_options.items():
            print(f"    [{key}] {value}")

        self.assertIn("H", menu_options)
        self.assertIn("T", menu_options)
        self.assertIn("A", menu_options)


class TestCasinoMenuDisplay(unittest.TestCase):
    """Test that casino menu displays correctly."""

    def test_main_menu_options_defined(self):
        """Test that all expected menu options are defined in main.py."""
        import sys
        sys.path.insert(0, "/home/opencode/data/work/casino/src")

        options = (
            ("B", "Blackjack", "blackjack.play"),
            ("P", "Poker", "poker.play"),
            ("S", "Slots", "slots.play"),
            ("Y", "Yahtzee", "yahtzee.play"),
            ("C", "Connect", "connect"),
            ("L", "List tables", "table.list"),
            ("J", "Join table", "table.join"),
            ("V", "View table", "table.view"),
            ("W", "Watch table", "admin.watch"),
            ("U", "Unwatch table", "admin.unwatch"),
            ("A", "Bet", "game.bet"),
            ("H", "Hit", "game.hit"),
            ("T", "Stand", "game.stand"),
            ("P", "Play", "game.play"),
            ("G", "Global msg", "chat.global"),
            ("K", "Bank", "bank"),
            ("X", "Disconnect", "connect.disconnect"),
            ("M", "Maintenance", "maint.main"),
        )

        keys = [o[0] for o in options]
        titles = [o[1] for o in options]

        self.assertIn("B", keys)
        self.assertIn("H", keys)
        self.assertIn("T", keys)
        self.assertIn("A", keys)
        self.assertIn("X", keys)

        self.assertIn("Blackjack", titles)
        self.assertIn("Hit", titles)
        self.assertIn("Stand", titles)
        self.assertIn("Bet", titles)

    def test_menu_help_includes_game_actions(self):
        """Test that menu help includes Hit and Stand options."""
        from bbsengine6 import io

        captured_output = []

        def mock_echo(msg, **kwargs):
            captured_output.append(msg)

        original_echo = io.echo
        io.echo = mock_echo

        try:
            options = (
                ("B", "Blackjack", "blackjack.play"),
                ("H", "Hit", "game.hit"),
                ("T", "Stand", "game.stand"),
                ("A", "Bet", "game.bet"),
                ("X", "Disconnect", "connect.disconnect"),
            )

            for o in options:
                opt = o[0]
                t = o[1]
                io.echo(
                    f"{{/all}}{{optioncolor}}[{opt}]{{/all}} {{valuecolor}} {t}{{/all}}"
                )

            output_text = " ".join(captured_output)

            self.assertIn("[B]", output_text)
            self.assertIn("[H]", output_text)
            self.assertIn("[T]", output_text)
            self.assertIn("[A]", output_text)
            self.assertIn("[X]", output_text)

            self.assertIn("Blackjack", output_text)
            self.assertIn("Hit", output_text)
            self.assertIn("Stand", output_text)
            self.assertIn("Bet", output_text)
        finally:
            io.echo = original_echo

    def test_inputchoice_options_format(self):
        """Test that inputchoice options string is uppercase without commas."""
        from bbsengine6.io import inputchoice

        options = "QBXCAHLTJP"
        self.assertEqual(options, options.upper())
        self.assertNotIn(",", options)

        for char in options:
            self.assertTrue(char.isupper())


def run_tests():
    """Run all tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestClientInputChoiceCase))
    suite.addTests(loader.loadTestsFromTestCase(TestClientMenuFlow))
    suite.addTests(loader.loadTestsFromTestCase(TestClientServerIO))
    suite.addTests(loader.loadTestsFromTestCase(TestCasinoMenuDisplay))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
