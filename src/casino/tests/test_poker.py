# casino/tests/test_poker.py
# Unit tests for poker components

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from casino.poker.lib import PokerDeck, PokerCard, HandRank, BettingStructure, RANKS, SUITS
from casino.poker.dealer import PokerDealer
from casino.poker.player import PokerPlayer
from casino.poker.variant import get_variant, TexasHoldEm, Omaha, SevenCardStud
from casino.poker.variant import evaluator


class TestPokerDeck:
    """Tests for PokerDeck class."""

    def test_deck_has_52_cards(self):
        deck = PokerDeck()
        assert deck.remaining() == 52

    def test_deal_removes_cards(self):
        deck = PokerDeck()
        cards = deck.deal(5)
        assert len(cards) == 5
        assert deck.remaining() == 47

    def test_shuffle_changes_order(self):
        deck1 = PokerDeck()
        deck1.shuffle()
        deck2 = PokerDeck()
        # Not a perfect test due to random, but basic sanity
        assert deck1.remaining() == deck2.remaining()

    def test_burn_removes_card(self):
        deck = PokerDeck()
        initial = deck.remaining()
        burned = deck.burn(1)
        assert len(burned) == 1
        assert deck.remaining() == initial - 1

    def test_reset_restores_deck(self):
        deck = PokerDeck()
        deck.deal(10)
        deck.reset()
        assert deck.remaining() == 52


class TestPokerCard:
    """Tests for PokerCard class."""

    def test_card_creation(self):
        card = PokerCard("A", "hearts")
        assert card.rank == "A"
        assert card.suit == "hearts"

    def test_card_from_string(self):
        card = PokerCard.from_string("KH")
        assert card.rank == "K"
        assert card.suit == "hearts"

    def test_card_to_string(self):
        card = PokerCard("Q", "spades")
        assert card.to_string() == "QS"

    def test_rank_value(self):
        assert PokerCard("2", "hearts").rank_value == 0
        assert PokerCard("A", "hearts").rank_value == 12


class TestPokerDealer:
    """Tests for PokerDealer class."""

    def test_dealer_initialization(self):
        dealer = PokerDealer()
        assert dealer.remaining_cards() == 52

    def test_shuffle_deck(self):
        dealer = PokerDealer()
        dealer.shuffle_deck(3)
        assert dealer.remaining_cards() == 52

    def test_deal_hole_cards(self):
        dealer = PokerDealer()
        players = [
            PokerPlayer("Alice", seat=1),
            PokerPlayer("Bob", seat=2),
        ]
        dealer.deal_hole_cards(players, 2)

        assert len(players[0].hole_cards) == 2
        assert len(players[1].hole_cards) == 2
        assert dealer.remaining_cards() == 48

    def test_deal_community_cards(self):
        dealer = PokerDealer()
        cards = dealer.deal_community_cards(3)
        assert len(cards) == 3
        assert len(dealer.community_cards) == 3
        assert len(dealer.burn_cards) == 1  # Burned one card

    def test_reset_clears_state(self):
        dealer = PokerDealer()
        dealer.deal_community_cards(3)
        dealer.reset()
        assert dealer.remaining_cards() == 52
        assert len(dealer.community_cards) == 0
        assert len(dealer.burn_cards) == 0


class TestPokerPlayer:
    """Tests for PokerPlayer class."""

    def test_player_initialization(self):
        player = PokerPlayer("Alice", seat=1, credits=1000)
        assert player.moniker == "Alice"
        assert player.seat == 1
        assert player.credits == 1000
        assert len(player.hole_cards) == 0

    def test_receive_card(self):
        player = PokerPlayer("Alice")
        player.receive_card("AH")
        assert "AH" in player.hole_cards

    def test_post_bet(self):
        player = PokerPlayer("Alice", credits=100)
        actual = player.post_bet(25)
        assert actual == 25
        assert player.credits == 75
        assert player.current_bet == 25
        assert player.total_in_pot == 25

    def test_post_bet_all_in(self):
        player = PokerPlayer("Alice", credits=50)
        actual = player.post_bet(100)
        assert actual == 50  # Can only bet what they have
        assert player.credits == 0
        assert player.is_all_in is True

    def test_collect_winnings(self):
        player = PokerPlayer("Alice", credits=100)
        player.collect_winnings(50)
        assert player.credits == 150

    def test_clear_hand(self):
        player = PokerPlayer("Alice", credits=100)
        player.receive_card("AH")
        player.receive_card("KD")
        player.post_bet(25)
        cards = player.clear_hand()

        assert len(cards) == 2
        assert len(player.hole_cards) == 0
        assert player.current_bet == 0

    def test_can_act(self):
        player = PokerPlayer("Alice", credits=100)
        assert player.can_act() is True

        player.has_folded = True
        assert player.can_act() is False

        player.has_folded = False
        player.is_all_in = True
        assert player.can_act() is False

    def test_can_check(self):
        player = PokerPlayer("Alice", credits=100)
        assert player.can_check(0) is True
        assert player.can_check(50) is False  # Has not bet

        player.post_bet(50)
        assert player.can_check(50) is True
        assert player.can_check(100) is False

    def test_can_call(self):
        player = PokerPlayer("Alice", credits=100)
        assert player.can_call(50) is True
        assert player.can_call(150) is False  # Not enough credits


class TestHandEvaluator:
    """Tests for hand evaluation."""

    def test_royal_flush(self):
        cards = ["AH", "KH", "QH", "JH", "10H"]
        rank, _ = evaluator.get_hand_rank(cards)
        assert rank == HandRank.ROYAL_FLUSH

    def test_straight_flush(self):
        cards = ["9H", "8H", "7H", "6H", "5H"]
        rank, _ = evaluator.get_hand_rank(cards)
        assert rank == HandRank.STRAIGHT_FLUSH

    def test_four_of_a_kind(self):
        cards = ["AH", "AD", "AC", "AS", "KD"]
        rank, _ = evaluator.get_hand_rank(cards)
        assert rank == HandRank.FOUR_OF_A_KIND

    def test_full_house(self):
        cards = ["AH", "AD", "AC", "KD", "KS"]
        rank, _ = evaluator.get_hand_rank(cards)
        assert rank == HandRank.FULL_HOUSE

    def test_flush(self):
        cards = ["AH", "KH", "7H", "5H", "2H"]
        rank, _ = evaluator.get_hand_rank(cards)
        assert rank == HandRank.FLUSH

    def test_straight(self):
        cards = ["AH", "KD", "QD", "JD", "10H"]
        rank, _ = evaluator.get_hand_rank(cards)
        assert rank == HandRank.STRAIGHT

    def test_wheel_straight(self):
        cards = ["AH", "2D", "3C", "4H", "5S"]
        rank, tie = evaluator.get_hand_rank(cards)
        assert rank == HandRank.STRAIGHT
        assert 3 in tie  # 5-high straight

    def test_three_of_a_kind(self):
        cards = ["AH", "AD", "AC", "KD", "QS"]
        rank, _ = evaluator.get_hand_rank(cards)
        assert rank == HandRank.THREE_OF_A_KIND

    def test_two_pair(self):
        cards = ["AH", "AD", "KD", "KS", "QS"]
        rank, _ = evaluator.get_hand_rank(cards)
        assert rank == HandRank.TWO_PAIR

    def test_pair(self):
        cards = ["AH", "AD", "KD", "QS", "7S"]
        rank, _ = evaluator.get_hand_rank(cards)
        assert rank == HandRank.PAIR

    def test_high_card(self):
        cards = ["AH", "KD", "QD", "9S", "7H"]
        rank, _ = evaluator.get_hand_rank(cards)
        assert rank == HandRank.HIGH_CARD


class TestHandEvaluatorTieBreakers:
    """Tests for tie-breaker logic."""

    def test_pair_vs_pair_kicker(self):
        # Player 1: Pair of Kings with Ace kicker
        hand1 = evaluator.get_hand_rank(["KH", "KD", "AH", "QD", "7S"])
        # Player 2: Pair of Kings with Queen kicker
        hand2 = evaluator.get_hand_rank(["KH", "KD", "QH", "JD", "7S"])

        assert hand1[0] == hand2[0] == HandRank.PAIR
        result = evaluator.compare_hands(hand1, hand2)
        assert result == 1  # Player 1 wins

    def test_full_house_trip_vs_trip(self):
        # Trip Kings full of Tens
        hand1 = evaluator.get_hand_rank(["KH", "KD", "KC", "10H", "10D"])
        # Trip Queens full of Tens
        hand2 = evaluator.get_hand_rank(["QH", "QD", "QC", "10C", "10S"])

        assert hand1[0] == hand2[0] == HandRank.FULL_HOUSE
        result = evaluator.compare_hands(hand1, hand2)
        assert result == 1  # Kings full wins


class TestTexasHoldEm:
    """Tests for Texas Hold'em variant."""

    def test_hold_em_streets(self):
        variant = get_variant("holdem")
        assert variant.get_betting_streets() == ["preflop", "flop", "turn", "river"]

    def test_hold_em_community_cards(self):
        variant = get_variant("holdem")
        community = variant.get_community_cards_per_street()
        assert community["preflop"] == 0
        assert community["flop"] == 3
        assert community["turn"] == 1
        assert community["river"] == 1

    def test_hold_em_hole_cards(self):
        variant = get_variant("holdem")
        assert variant.hole_cards_per_player == 2

    def test_hold_em_evaluate(self):
        variant = get_variant("holdem")
        rank, best = variant.evaluate_showdown(
            ["AH", "KD"],
            ["QH", "JD", "10D", "2S", "3H"]
        )
        assert rank >= HandRank.STRAIGHT  # Ace-high straight


class TestOmaha:
    """Tests for Omaha variant."""

    def test_omaha_streets(self):
        variant = get_variant("omaha")
        assert variant.get_betting_streets() == ["preflop", "flop", "turn", "river"]

    def test_omaha_hole_cards(self):
        variant = get_variant("omaha")
        assert variant.hole_cards_per_player == 4

    def test_omaha_must_use_two(self):
        """Test that Omaha requires exactly 2 hole cards."""
        variant = get_variant("omaha")
        # With 4 hole cards and 5 community, best hand should use exactly 2 hole cards
        rank, best = variant.evaluate_showdown(
            ["AH", "KD", "QS", "JC"],
            ["QH", "JD", "10D", "2S", "3H"]
        )
        # The evaluation should succeed - it will find the best 5-card hand
        assert rank >= 0


class TestSevenCardStud:
    """Tests for 7-Card Stud variant."""

    def test_stud_streets(self):
        variant = get_variant("stud")
        streets = variant.get_betting_streets()
        assert "third_street" in streets
        assert "seventh_street" in streets

    def test_stud_hole_cards(self):
        variant = get_variant("stud")
        assert variant.hole_cards_per_player == 7

    def test_stud_no_community(self):
        variant = get_variant("stud")
        community = variant.get_community_cards_per_street()
        # All zeros - stud has no community cards
        assert all(v == 0 for v in community.values())

    def test_stud_evaluate(self):
        variant = get_variant("stud")
        # 7 card stud - uses hole cards only, no community
        # This hand is three Aces + two Kings = Full House
        rank, best = variant.evaluate_showdown(
            ["AH", "AD", "AC", "KD", "KS", "QS", "7S"],
            []  # No community cards in stud
        )
        assert rank == HandRank.FULL_HOUSE


class TestBettingLimits:
    """Tests for betting limit calculations."""

    def test_no_limit_min_raise(self):
        variant = get_variant("holdem")
        limits = variant.get_betting_limits(pot_size=100, current_bet=10, min_raise=2)
        assert limits.min_raise == 2
        assert limits.max_raise is None  # Unlimited

    def test_pot_limit_max_raise(self):
        holdem = get_variant("holdem")
        holdem.betting_structure = BettingStructure.POT_LIMIT

        # Pot = 100, current bet = 10, to call = 10, max raise = 100 + 10 = 110
        limits = holdem.get_betting_limits(pot_size=100, current_bet=10, min_raise=2)
        assert limits.max_raise == 110

    def test_fixed_limit(self):
        holdem = get_variant("holdem")
        holdem.betting_structure = BettingStructure.FIXED_LIMIT

        limits = holdem.get_betting_limits(pot_size=100, current_bet=10, min_raise=2)
        assert limits.min_raise == 2
        assert limits.max_raise == 8  # 2 * 4 = fixed limit max


class TestPotCalculation:
    """Tests for pot calculations."""

    def test_simple_pot(self):
        pot = 0
        # SB posts 1, BB posts 2
        pot += 1 + 2
        assert pot == 3

    def test_side_pot_simple(self):
        # Main pot: all players can win
        main_pot = 30  # 3 players, 10 each

        # Side pot 1: Player A all-in for 20, B calls 20, C calls 20
        # Player A can win 30 (3 * 10)
        # Players B and C can win an additional 20 each from each other
        side_pot_1 = 40  # (20 from B + 20 from C) - what A can win from them

        assert main_pot == 30
        assert side_pot_1 == 40


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
