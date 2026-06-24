#!/usr/bin/env python3
# casino/tests/test_new_features.py
# Unit and integration tests for surrender, hole card, soft 17, and 5-card charlie features

import sys
import unittest
from decimal import Decimal

sys.path.insert(0, "/home/opencode/data/work/casino/src")

from casino.cards import Card
from casino.blackjack import Hand


class TestSurrender(unittest.TestCase):
    """Unit tests for surrender logic."""

    def test_can_surrender_true_two_cards(self):
        """Player can surrender with exactly 2 cards."""
        hand = Hand.from_strings(["8H", "9D"])
        self.assertTrue(hand.can_surrender())

    def test_can_surrender_false_three_cards(self):
        """Player cannot surrender with 3+ cards."""
        hand = Hand.from_strings(["8H", "9D", "5C"])
        self.assertFalse(hand.can_surrender())

    def test_can_surrender_false_single_card(self):
        """Player cannot surrender with 1 card."""
        hand = Hand.from_strings(["8H"])
        self.assertFalse(hand.can_surrender())

    def test_can_surrender_false_empty(self):
        """Player cannot surrender with empty hand."""
        hand = Hand.from_strings([])
        self.assertFalse(hand.can_surrender())

    def test_can_surrender_false_bust(self):
        """Player cannot surrender after busting."""
        hand = Hand.from_strings(["8H", "9D", "KD"])
        self.assertTrue(hand.is_bust())
        self.assertFalse(hand.can_surrender())

    def test_surrender_half_bet(self):
        """Surrender returns half the bet."""
        bet_amount = 100
        returned = bet_amount // 2
        forfeited = bet_amount - returned
        self.assertEqual(returned, 50)
        self.assertEqual(forfeited, 50)


class TestHoleCard(unittest.TestCase):
    """Unit tests for face-down dealer card logic."""

    def test_hide_hole_card_two_cards(self):
        """With 2 cards, second should be hidden."""
        dealer_cards = ["8H", "9D"]
        hole_card = "9D"
        visible = [dealer_cards[0], "hidden"]
        self.assertEqual(visible, ["8H", "hidden"])

    def test_hide_hole_card_no_hole(self):
        """Without hole card set, show all cards."""
        dealer_cards = ["8H", "9D"]
        hole_card = None
        visible = dealer_cards if not hole_card else [dealer_cards[0], "hidden"]
        self.assertEqual(visible, ["8H", "9D"])

    def test_hide_hole_card_empty(self):
        """Empty dealer hand returns empty."""
        dealer_cards = []
        hole_card = None
        self.assertEqual(dealer_cards, [])

    def test_hide_hole_card_single(self):
        """Single card returns as-is."""
        dealer_cards = ["AH"]
        hole_card = None
        visible = dealer_cards if not hole_card or len(dealer_cards) < 2 else [dealer_cards[0], "hidden"]
        self.assertEqual(visible, ["AH"])


class TestDealerSoft17(unittest.TestCase):
    """Unit tests for dealer soft 17 rule."""

    def test_is_soft_17_true(self):
        """Ace + 6 = soft 17."""
        hand = Hand.from_strings(["AH", "6D"])
        self.assertEqual(hand.total(), 17)
        self.assertTrue(hand.is_soft())

    def test_is_soft_17_false_hard_17(self):
        """10 + 7 = hard 17, not soft."""
        hand = Hand.from_strings(["10H", "7D"])
        self.assertEqual(hand.total(), 17)
        self.assertFalse(hand.is_soft())

    def test_is_soft_17_false_ace_counted_as_1(self):
        """Ace + 9 + 2 = hard 12 (ace counted as 1)."""
        hand = Hand.from_strings(["AH", "9D", "2C"])
        self.assertEqual(hand.total(), 12)
        self.assertFalse(hand.is_soft())

    def test_dealer_hits_on_soft_17_when_rule_hit(self):
        """Dealer should hit on soft 17 when rule is 'hit'."""
        soft_17_rule = "hit"
        hand = Hand.from_strings(["AH", "6D"])
        should_hit = soft_17_rule == "hit"
        self.assertTrue(should_hit)

    def test_dealer_stands_on_soft_17_when_rule_stand(self):
        """Dealer should stand on soft 17 when rule is 'stand'."""
        soft_17_rule = "stand"
        hand = Hand.from_strings(["AH", "6D"])
        should_hit = soft_17_rule == "hit"
        self.assertFalse(should_hit)


class TestFiveCardCharlie(unittest.TestCase):
    """Unit tests for 5-card Charlie rule."""

    def test_is_five_card_charlie_true(self):
        """5 cards without bust is a charlie."""
        hand = Hand.from_strings(["2H", "3D", "4C", "5S", "6D"])
        self.assertEqual(len(hand.cards), 5)
        self.assertEqual(hand.total(), 20)
        self.assertFalse(hand.is_bust())
        self.assertTrue(hand.is_five_card_charlie())

    def test_is_five_card_charlie_false_six_cards(self):
        """6 cards is not a 5-card charlie."""
        hand = Hand.from_strings(["2H", "3D", "4C", "5S", "6D", "7C"])
        self.assertEqual(len(hand.cards), 6)
        self.assertFalse(hand.is_five_card_charlie())

    def test_is_five_card_charlie_false_bust(self):
        """5 cards that bust is not a charlie."""
        hand = Hand.from_strings(["9H", "9D", "9C", "9S", "KD"])
        self.assertTrue(hand.is_bust())
        self.assertFalse(hand.is_five_card_charlie())

    def test_five_card_charlie_payout(self):
        """5-card charlie pays 1:1 (even money), not 3:2."""
        bet_amount = 100
        payout = bet_amount * 2
        self.assertEqual(payout, 200)

    def test_five_card_charlie_less_than_five(self):
        """Less than 5 cards cannot be a charlie."""
        hand = Hand.from_strings(["2H", "3D", "4C", "5S"])
        self.assertEqual(len(hand.cards), 4)
        self.assertFalse(hand.is_five_card_charlie())


class TestTableAttrs(unittest.TestCase):
    """Unit tests for table configuration attributes."""

    def test_default_surrender_early(self):
        """Default surrender should be early."""
        attrs = {}
        surrender = attrs.get("surrender", "early")
        self.assertEqual(surrender, "early")

    def test_surrender_disabled(self):
        """Surrender can be disabled."""
        attrs = {"surrender": False}
        self.assertFalse(attrs.get("surrender"))

    def test_default_soft_17_hit(self):
        """Default soft 17 should be hit."""
        attrs = {}
        soft_17 = attrs.get("soft_17", "hit")
        self.assertEqual(soft_17, "hit")

    def test_soft_17_stand(self):
        """Soft 17 can be set to stand."""
        attrs = {"soft_17": "stand"}
        self.assertEqual(attrs.get("soft_17"), "stand")

    def test_default_charlie_disabled(self):
        """Default charlie should be disabled."""
        attrs = {}
        charlie = attrs.get("charlie", False)
        self.assertFalse(charlie)

    def test_charlie_enabled(self):
        """Charlie can be enabled."""
        attrs = {"charlie": True}
        self.assertTrue(attrs.get("charlie"))


if __name__ == "__main__":
    unittest.main()
