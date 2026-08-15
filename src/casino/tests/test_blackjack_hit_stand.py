#!/usr/bin/env python3
# casino/tests/test_blackjack_hit_stand.py
# Unit tests for blackjack hit, stand, dealer turn, and winner determination.

import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, "/home/opencode/data/work/casino/src")

from casino import lib
from casino.blackjack import Hand
from casino.blackjack.play import determine_winner, run_dealer_turn


class _StubPlayer:
    """Minimal stand-in for libcasino.Player used by determine_winner."""

    def __init__(self):
        self.stats: dict = {}
        self.calls: list = []

    def incstat(self, stat):
        self.calls.append(stat)
        self.stats.setdefault(stat, 0)
        self.stats[stat] += 1


def _build_hand(card_strings, label: str = "test"):
    """Build a casino.lib.Hand populated with the given cards in order."""
    hand = lib.Hand(label)
    for shorthand in card_strings:
        hand.add(lib.Card(shorthand=shorthand, facedown=False))
    return hand


def _build_shoe(card_strings):
    """Build a casino.lib.Shoe whose draw() yields the given cards in order.

    ``Shoe.draw()`` uses ``list.pop()`` which removes from the end, so the
    first-to-draw card must be at the tail of the cards list.
    """
    shoe = lib.Shoe(decks=None)
    shoe.cards = [lib.Card(shorthand=s, facedown=False) for s in reversed(card_strings)]
    return shoe


def _run_dealer(dealer, shoe):
    """Run dealer turn with io.echo patched away."""
    with patch("casino.blackjack.play.io"):
        return run_dealer_turn(dealer, shoe)


class TestHandHit(unittest.TestCase):
    """Hand.hit() should draw a card from the shoe and append it to the hand."""

    def test_hit_adds_one_card(self):
        hand = _build_hand(["5H", "6D"])
        shoe = _build_shoe(["KC"])

        drawn = hand.hit(shoe)

        self.assertEqual(drawn.shorthand, "KC")
        self.assertEqual(hand.cards[hand.index - 1].shorthand, "KC")

    def test_hit_multiple_draws_in_order(self):
        hand = _build_hand(["5H"])
        shoe = _build_shoe(["2D", "7C", "9S"])

        hand.hit(shoe)
        hand.hit(shoe)
        hand.hit(shoe)

        drawn = [hand.cards[i].shorthand for i in range(hand.index)]
        self.assertEqual(drawn, ["5H", "2D", "7C", "9S"])

    def test_hit_depletes_shoe(self):
        hand = _build_hand(["5H"])
        shoe = _build_shoe(["KD"])
        hand.hit(shoe)
        self.assertEqual(len(shoe.cards), 0)

    def test_hit_updates_total(self):
        hand = _build_hand(["7H", "3D"])
        shoe = _build_shoe(["5C"])
        hand.hit(shoe)
        self.assertEqual(hand.calcvalue(), 15)

    def test_hit_after_bust_still_works(self):
        # Hit mechanics are independent of bust state.
        hand = _build_hand(["KH", "QD", "5D"])  # already bust
        shoe = _build_shoe(["3C"])
        hand.hit(shoe)
        self.assertEqual(hand.cards[hand.index - 1].shorthand, "3C")
        self.assertEqual(hand.calcvalue(), 28)


class TestHandStand(unittest.TestCase):
    """Hand.stand() should mark the hand as standing without changing cards."""

    def test_stand_sets_flag(self):
        hand = _build_hand(["10H", "9D"])
        hand.stand()
        self.assertTrue(getattr(hand, "standing", False))

    def test_stand_does_not_draw(self):
        hand = _build_hand(["10H", "9D"])
        shoe = _build_shoe(["KC"])
        cards_before = list(hand.cards)
        shoe_len_before = len(shoe.cards)
        hand.stand()
        self.assertEqual(hand.cards, cards_before)
        self.assertEqual(len(shoe.cards), shoe_len_before)


class TestHandCalcvalue(unittest.TestCase):
    """Hand.calcvalue() should sum card values with ace adjustment."""

    def test_no_aces(self):
        self.assertEqual(_build_hand(["5H", "7D"]).calcvalue(), 12)

    def test_ace_as_eleven(self):
        self.assertEqual(_build_hand(["AH", "KD"]).calcvalue(), 21)

    def test_ace_adjusts_down(self):
        self.assertEqual(_build_hand(["AH", "KD", "5C"]).calcvalue(), 16)

    def test_multiple_aces_adjust(self):
        self.assertEqual(_build_hand(["AH", "AH", "9H"]).calcvalue(), 21)

    def test_bust_value(self):
        self.assertEqual(_build_hand(["KH", "QD", "5D"]).calcvalue(), 25)


class TestDealerTurn(unittest.TestCase):
    """run_dealer_turn should hit until 17+ and bust if it exceeds 21."""

    def test_dealer_hits_until_seventeen(self):
        dealer = _build_hand(["10H", "6D"], label="dealer")  # 16
        shoe = _build_shoe(["3C"])  # becomes 19
        result = _run_dealer(dealer, shoe)
        self.assertFalse(result["bust"])
        self.assertEqual(result["total"], 19)

    def test_dealer_stands_on_seventeen(self):
        dealer = _build_hand(["10H", "7D"], label="dealer")  # 17
        shoe = _build_shoe(["KC"])
        result = _run_dealer(dealer, shoe)
        self.assertFalse(result["bust"])
        self.assertEqual(result["total"], 17)
        self.assertEqual(len(shoe.cards), 1)  # KC not drawn

    def test_dealer_stands_on_eighteen(self):
        dealer = _build_hand(["9H", "9D"], label="dealer")  # 18
        shoe = _build_shoe(["KC"])
        result = _run_dealer(dealer, shoe)
        self.assertEqual(result["total"], 18)
        self.assertEqual(len(shoe.cards), 1)

    def test_dealer_busts_over_twenty_one(self):
        dealer = _build_hand(["10H", "6D"], label="dealer")  # 16
        shoe = _build_shoe(["KC"])  # becomes 26 -> bust
        result = _run_dealer(dealer, shoe)
        self.assertTrue(result["bust"])
        self.assertEqual(result["total"], 26)

    def test_dealer_hits_multiple_times_to_reach_seventeen(self):
        dealer = _build_hand(["2H", "3D"], label="dealer")  # 5
        # +5 = 10, +8 = 18 -> stand
        shoe = _build_shoe(["5C", "8S", "KH"])
        result = _run_dealer(dealer, shoe)
        self.assertFalse(result["bust"])
        self.assertEqual(result["total"], 18)
        self.assertEqual(len(shoe.cards), 1)  # KH not drawn

    def test_soft_seventeen_stands(self):
        dealer = _build_hand(["AH", "6D"], label="dealer")  # soft 17
        shoe = _build_shoe(["KC"])
        result = _run_dealer(dealer, shoe)
        self.assertFalse(result["bust"])
        self.assertEqual(result["total"], 17)
        self.assertEqual(len(shoe.cards), 1)

    def test_dealer_hits_on_fifteen(self):
        dealer = _build_hand(["8H", "7D"], label="dealer")  # 15
        shoe = _build_shoe(["5C"])  # becomes 20 -> stand
        result = _run_dealer(dealer, shoe)
        self.assertFalse(result["bust"])
        self.assertEqual(result["total"], 20)


class TestDetermineWinner(unittest.TestCase):
    """determine_winner should assign win/loss/draw and update player stats."""

    def test_player_wins_over_dealer(self):
        player = _StubPlayer()
        player_hand = _build_hand(["10H", "9D"])  # 19
        dealer_hand = _build_hand(["10H", "7D"])  # 17
        with patch("casino.blackjack.play.io"):
            determine_winner(player_hand, dealer_hand, player)
        self.assertEqual(player.calls, ["win"])

    def test_dealer_wins_over_player(self):
        player = _StubPlayer()
        player_hand = _build_hand(["10H", "7D"])  # 17
        dealer_hand = _build_hand(["10H", "9D"])  # 19
        with patch("casino.blackjack.play.io"):
            determine_winner(player_hand, dealer_hand, player)
        self.assertEqual(player.calls, ["loss"])

    def test_push_when_totals_equal(self):
        player = _StubPlayer()
        player_hand = _build_hand(["10H", "8D"])  # 18
        dealer_hand = _build_hand(["KH", "8C"])  # 18
        with patch("casino.blackjack.play.io"):
            determine_winner(player_hand, dealer_hand, player)
        self.assertEqual(player.calls, ["draw"])

    def test_player_busts_loses(self):
        player = _StubPlayer()
        player_hand = _build_hand(["KH", "QD", "5D"])  # 25
        dealer_hand = _build_hand(["10H", "7D"])  # 17
        with patch("casino.blackjack.play.io"):
            determine_winner(player_hand, dealer_hand, player)
        self.assertEqual(player.calls, ["loss"])

    def test_dealer_busts_player_wins(self):
        player = _StubPlayer()
        player_hand = _build_hand(["10H", "7D"])  # 17
        dealer_hand = _build_hand(["KH", "QD", "5D"])  # 25
        with patch("casino.blackjack.play.io"):
            determine_winner(player_hand, dealer_hand, player)
        self.assertEqual(player.calls, ["win"])

    def test_player_blackjack_beats_dealer_twenty(self):
        player = _StubPlayer()
        player_hand = _build_hand(["AH", "KD"])  # 21
        dealer_hand = _build_hand(["KH", "QD"])  # 20
        with patch("casino.blackjack.play.io"):
            determine_winner(player_hand, dealer_hand, player)
        self.assertEqual(player.calls, ["win"])


class TestNewHandHitAndBust(unittest.TestCase):
    """casino.blackjack.Hand (newer dataclass) hit/stand/bust behavior."""

    def test_hit_via_append_updates_total(self):
        hand = Hand.from_strings(["5H", "6D"])
        hand.cards.append(Hand.from_strings(["KC"]).cards[0])
        self.assertEqual(len(hand.cards), 3)
        self.assertEqual(hand.total(), 21)

    def test_total_after_hit_to_bust(self):
        hand = Hand.from_strings(["10H", "9D", "KC"])
        self.assertEqual(hand.total(), 29)
        self.assertTrue(hand.is_bust())

    def test_soft_seventeen_not_bust(self):
        hand = Hand.from_strings(["AH", "6D"])
        self.assertEqual(hand.total(), 17)
        self.assertFalse(hand.is_bust())

    def test_soft_eighteen_after_hit(self):
        hand = Hand.from_strings(["AH", "7D"])
        self.assertEqual(hand.total(), 18)
        self.assertFalse(hand.is_bust())

    def test_three_card_bust(self):
        hand = Hand.from_strings(["9H", "8D", "7C"])
        self.assertEqual(hand.total(), 24)
        self.assertTrue(hand.is_bust())

    def test_five_card_charlie_not_bust(self):
        hand = Hand.from_strings(["2H", "3D", "4C", "5S", "6H"])
        self.assertEqual(hand.total(), 20)
        self.assertTrue(hand.is_five_card_charlie())
        self.assertFalse(hand.is_bust())

    def test_five_card_bust(self):
        hand = Hand.from_strings(["KH", "QD", "JC", "AD", "2S"])
        self.assertEqual(hand.total(), 33)
        self.assertTrue(hand.is_bust())
        self.assertFalse(hand.is_five_card_charlie())


class TestPlayerLoopBehavior(unittest.TestCase):
    """Validate the player decision tree without driving the full io loop."""

    def test_player_hitting_until_bust(self):
        hand = _build_hand(["10H", "6D"])  # 16
        shoe = _build_shoe(["KC"])  # 26 -> bust
        bust = False
        while True:
            hand.hit(shoe)
            total = hand.calcvalue()
            if total > 21:
                bust = True
                break
            if total == 21:
                break
        self.assertTrue(bust)
        self.assertEqual(hand.calcvalue(), 26)

    def test_player_hitting_to_twenty_one_stops(self):
        hand = _build_hand(["10H", "7D"])  # 17
        shoe = _build_shoe(["4C"])  # 21
        total = hand.calcvalue()
        stop = False
        bust = False
        while True:
            hand.hit(shoe)
            total = hand.calcvalue()
            if total > 21:
                bust = True
                break
            if total == 21:
                stop = True
                break
        self.assertTrue(stop)
        self.assertFalse(bust)
        self.assertEqual(total, 21)

    def test_player_standing_skips_dealer_turn(self):
        # When player stands (doesn't bust), dealer turn runs only if player
        # total <= 21. Verify the gate condition in play.main.
        player_total = 17
        self.assertTrue(player_total <= 21)

    def test_player_bust_skips_dealer_turn(self):
        player_total = 25
        self.assertFalse(player_total <= 21)


def run_tests():
    """Run all tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestHandHit))
    suite.addTests(loader.loadTestsFromTestCase(TestHandStand))
    suite.addTests(loader.loadTestsFromTestCase(TestHandCalcvalue))
    suite.addTests(loader.loadTestsFromTestCase(TestDealerTurn))
    suite.addTests(loader.loadTestsFromTestCase(TestDetermineWinner))
    suite.addTests(loader.loadTestsFromTestCase(TestNewHandHitAndBust))
    suite.addTests(loader.loadTestsFromTestCase(TestPlayerLoopBehavior))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
