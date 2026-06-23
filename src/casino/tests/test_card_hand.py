#!/usr/bin/env python3
# casino/tests/test_card_hand.py
# Unit tests demonstrating Card, Hand, and GamePhase features

import sys
import unittest

sys.path.insert(0, "/home/opencode/data/work/casino/src")

from casino.cards import Card, Pips, Suit
from casino.blackjack import Hand, GamePhase


class TestCard(unittest.TestCase):
    """Test Card dataclass."""

    def test_from_string_2_char(self):
        card = Card.from_string("AH")
        self.assertEqual(card.pips, "A")
        self.assertEqual(card.suit, "H")
        self.assertFalse(card.facedown)

    def test_from_string_3_char(self):
        card = Card.from_string("10S")
        self.assertEqual(card.pips, "10")
        self.assertEqual(card.suit, "S")
        self.assertFalse(card.facedown)

    def test_from_string_facedown(self):
        card = Card.from_string("KD", facedown=True)
        self.assertEqual(card.pips, "K")
        self.assertEqual(card.suit, "D")
        self.assertTrue(card.facedown)

    def test_from_string_invalid(self):
        with self.assertRaises(ValueError):
            Card.from_string("invalid")

    def test_str(self):
        self.assertEqual(str(Card.from_string("AH")), "AH")
        self.assertEqual(str(Card.from_string("10S")), "10S")

    def test_value_ace(self):
        self.assertEqual(Card.from_string("AH").value, 11)

    def test_value_face_cards(self):
        self.assertEqual(Card.from_string("JH").value, 10)
        self.assertEqual(Card.from_string("QH").value, 10)
        self.assertEqual(Card.from_string("KH").value, 10)

    def test_value_number_cards(self):
        self.assertEqual(Card.from_string("2H").value, 2)
        self.assertEqual(Card.from_string("7D").value, 7)
        self.assertEqual(Card.from_string("9C").value, 9)


class TestHand(unittest.TestCase):
    """Test Hand class."""

    def test_from_strings(self):
        hand = Hand.from_strings(["AH", "KD"])
        self.assertEqual(len(hand.cards), 2)
        self.assertEqual(hand.cards[0].pips, "A")
        self.assertEqual(hand.cards[1].pips, "K")

    def test_to_strings(self):
        hand = Hand.from_strings(["AH", "KD", "10S"])
        self.assertEqual(hand.to_strings(), ["AH", "KD", "10S"])

    def test_total_no_aces(self):
        hand = Hand.from_strings(["7H", "8D"])
        self.assertEqual(hand.total(), 15)

    def test_total_with_aces(self):
        hand = Hand.from_strings(["AH", "KD"])
        self.assertEqual(hand.total(), 21)

    def test_total_aces_adjust(self):
        hand = Hand.from_strings(["AH", "AH", "9H"])
        self.assertEqual(hand.total(), 21)

    def test_total_multiple_aces_adjust(self):
        hand = Hand.from_strings(["AH", "AH", "AH", "KH"])
        self.assertEqual(hand.total(), 13)

    def test_is_bust(self):
        hand = Hand.from_strings(["KH", "QD", "5D"])
        self.assertTrue(hand.is_bust())

    def test_is_bust_false(self):
        hand = Hand.from_strings(["7H", "8D"])
        self.assertFalse(hand.is_bust())

    def test_is_blackjack(self):
        hand = Hand.from_strings(["AH", "KD"])
        self.assertTrue(hand.is_blackjack())

    def test_is_blackjack_21_not_2_cards(self):
        hand = Hand.from_strings(["AH", "5D", "6H"])
        self.assertFalse(hand.is_blackjack())

    def test_is_natural(self):
        hand = Hand.from_strings(["AH", "KD"])
        self.assertTrue(hand.is_natural())

    def test_can_split_true(self):
        hand = Hand.from_strings(["8H", "8D"])
        self.assertTrue(hand.can_split())

    def test_can_split_false_different_ranks(self):
        hand = Hand.from_strings(["8H", "9D"])
        self.assertFalse(hand.can_split())

    def test_can_split_false_more_than_2_cards(self):
        hand = Hand.from_strings(["8H", "8D", "5C"])
        self.assertFalse(hand.can_split())

    def test_can_double_down_true(self):
        hand = Hand.from_strings(["7H", "8D"])
        self.assertTrue(hand.can_double_down())

    def test_can_double_down_false(self):
        hand = Hand.from_strings(["7H", "8D", "5C"])
        self.assertFalse(hand.can_double_down())

    def test_is_split_hand(self):
        hand = Hand.from_strings(["8H", "8D"], is_split=True)
        self.assertTrue(hand.is_split_hand())

    def test_is_split_hand_false(self):
        hand = Hand.from_strings(["8H", "8D"], is_split=False)
        self.assertFalse(hand.is_split_hand())


class TestGamePhase(unittest.TestCase):
    """Test GamePhase enum."""

    def test_values(self):
        self.assertEqual(GamePhase.WAITING.value, "waiting")
        self.assertEqual(GamePhase.BETTING.value, "betting")
        self.assertEqual(GamePhase.PLAYING.value, "playing")
        self.assertEqual(GamePhase.SETTLING.value, "settling")
        self.assertEqual(GamePhase.SETTLED.value, "settled")

    def test_from_string(self):
        self.assertEqual(GamePhase.from_string("playing"), GamePhase.PLAYING)
        self.assertEqual(GamePhase.from_string("SETTLED"), GamePhase.SETTLED)

    def test_from_string_invalid(self):
        with self.assertRaises(ValueError):
            GamePhase.from_string("invalid")

    def test_str(self):
        self.assertEqual(str(GamePhase.PLAYING), "playing")


def run_tests():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestCard))
    suite.addTests(loader.loadTestsFromTestCase(TestHand))
    suite.addTests(loader.loadTestsFromTestCase(TestGamePhase))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
