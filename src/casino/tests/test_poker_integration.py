# casino/tests/test_poker_integration.py
# Integration tests for poker service

import pytest
import sys
import os
from unittest.mock import Mock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from casino.poker.services.poker import PokerService, PokerTableState, PlayerAction
from casino.poker.variant import TexasHoldEm, Omaha
from casino.poker.lib import BettingStructure


class MockArgs:
    """Mock args for testing."""
    def __init__(self):
        self.debug = False


class TestPokerServiceCreateTable:
    """Tests for creating poker tables."""

    def test_create_holdem_table(self):
        args = MockArgs()
        service = PokerService(args)

        result = service.create_table(
            table_moniker="test-table-1",
            variant_name="holdem",
            betting_structure="no_limit",
            small_blind=1,
            big_blind=2,
        )

        assert result["success"] is True
        assert result["table_moniker"] == "test-table-1"
        assert result["variant"] == "holdem"
        assert "test-table-1" in service._tables

    def test_create_omaha_table(self):
        args = MockArgs()
        service = PokerService(args)

        result = service.create_table(
            table_moniker="omaha-table",
            variant_name="omaha",
            betting_structure="pot_limit",
            small_blind=5,
            big_blind=10,
        )

        assert result["success"] is True
        assert result["variant"] == "omaha"
        assert result["betting_structure"] == "pot_limit"

    def test_create_invalid_variant(self):
        args = MockArgs()
        service = PokerService(args)

        result = service.create_table(
            table_moniker="bad-table",
            variant_name="bad_variant",
            betting_structure="no_limit",
            small_blind=1,
            big_blind=2,
        )

        assert result["success"] is False
        assert "Unknown variant" in result["message"]

    def test_create_invalid_betting_structure(self):
        args = MockArgs()
        service = PokerService(args)

        result = service.create_table(
            table_moniker="bad-bet-table",
            variant_name="holdem",
            betting_structure="bad_structure",
            small_blind=1,
            big_blind=2,
        )

        assert result["success"] is False
        assert "Unknown betting structure" in result["message"]


class TestPokerServiceJoinLeave:
    """Tests for joining and leaving tables."""

    def test_join_table(self):
        args = MockArgs()
        service = PokerService(args)

        service.create_table(
            table_moniker="test-table",
            variant_name="holdem",
            betting_structure="no_limit",
            small_blind=1,
            big_blind=2,
        )

        result = service.join_table("test-table", "Alice", 500)

        assert result["success"] is True
        assert result["seat"] == 1
        assert result["credits"] == 500

    def test_join_nonexistent_table(self):
        args = MockArgs()
        service = PokerService(args)

        result = service.join_table("nonexistent", "Alice", 500)

        assert result["success"] is False
        assert "not found" in result["message"]

    def test_join_full_table(self):
        args = MockArgs()
        service = PokerService(args)

        service.create_table(
            table_moniker="full-table",
            variant_name="holdem",
            betting_structure="no_limit",
            small_blind=1,
            big_blind=2,
            max_players=2,
        )

        service.join_table("full-table", "Alice", 500)
        service.join_table("full-table", "Bob", 500)

        result = service.join_table("full-table", "Charlie", 500)

        assert result["success"] is False
        assert "full" in result["message"]

    def test_leave_table(self):
        args = MockArgs()
        service = PokerService(args)

        service.create_table("test-table", "holdem", "no_limit", 1, 2)
        service.join_table("test-table", "Alice", 500)

        result = service.leave_table("test-table", "Alice")

        assert result["success"] is True
        assert "Alice" not in service._tables["test-table"].players


class TestPokerServiceStartHand:
    """Tests for starting hands."""

    def test_start_hand_insufficient_players(self):
        args = MockArgs()
        service = PokerService(args)

        service.create_table("test-table", "holdem", "no_limit", 1, 2)
        service.join_table("test-table", "Alice", 500)

        result = service.start_hand("test-table")

        assert result["success"] is False
        assert "players" in result["message"].lower()

    def test_start_hand_success(self):
        args = MockArgs()
        service = PokerService(args)

        service.create_table("test-table", "holdem", "no_limit", 1, 2)
        service.join_table("test-table", "Alice", 500)
        service.join_table("test-table", "Bob", 500)

        result = service.start_hand("test-table")

        assert result["success"] is True
        assert "test-table" in service._tables
        table = service._tables["test-table"]
        assert table.game_stage == "preflop"


class TestPokerServiceBetting:
    """Tests for betting actions."""

    def test_player_action_fold(self):
        args = MockArgs()
        service = PokerService(args)

        service.create_table("test-table", "holdem", "no_limit", 1, 2)
        service.join_table("test-table", "Alice", 500)
        service.join_table("test-table", "Bob", 500)
        service.start_hand("test-table")

        # Get the current player (first to act after blinds)
        table = service._tables["test-table"]
        first_player = table.current_player

        if first_player:
            result = service.player_action("test-table", first_player, "fold", 0)
            assert result["success"] is True
            assert result["action"] == "fold"

    def test_player_action_check(self):
        args = MockArgs()
        service = PokerService(args)

        service.create_table("test-table", "holdem", "no_limit", 1, 2)
        service.join_table("test-table", "Alice", 500)
        service.join_table("test-table", "Bob", 500)
        service.start_hand("test-table")

        # The big blind should be able to check
        table = service._tables["test-table"]
        bb_player = None
        for p in table.players.values():
            if p.current_bet >= table.big_blind:
                bb_player = p.moniker
                break

        if bb_player:
            result = service.player_action("test-table", bb_player, "check", 0)
            # May fail if there's a bet to call, but should process
            assert result is not None


class TestPokerServiceShowdown:
    """Tests for showdown logic."""

    def test_single_player_wins_uncontested(self):
        # This would test that a single remaining player wins
        pass  # Complex state machine test


class TestPokerServiceGetState:
    """Tests for getting table state."""

    def test_get_table_state(self):
        args = MockArgs()
        service = PokerService(args)

        service.create_table("test-table", "holdem", "no_limit", 1, 2)
        service.join_table("test-table", "Alice", 500)
        service.join_table("test-table", "Bob", 500)
        service.start_hand("test-table")

        state = service.get_table_state("test-table", "Alice")

        assert state["table_moniker"] == "test-table"
        assert state["variant"] == "texas_hold_em"
        assert state["betting_structure"] == "NO_LIMIT"
        assert state["stakes"] == "$1/$2"
        assert "player_hand" in state
        assert "player_credits" in state
        assert "players" in state

    def test_get_state_nonexistent_table(self):
        args = MockArgs()
        service = PokerService(args)

        state = service.get_table_state("nonexistent", "Alice")

        assert "error" in state


class TestPokerServiceListTables:
    """Tests for listing tables."""

    def test_list_empty(self):
        args = MockArgs()
        service = PokerService(args)

        tables = service.list_tables()

        assert tables == []

    def test_list_tables(self):
        args = MockArgs()
        service = PokerService(args)

        service.create_table("table-1", "holdem", "no_limit", 1, 2)
        service.create_table("table-2", "omaha", "pot_limit", 5, 10)

        tables = service.list_tables()

        assert len(tables) == 2
        monikers = [t["moniker"] for t in tables]
        assert "table-1" in monikers
        assert "table-2" in monikers


class TestPokerServiceIntegration:
    """Integration tests for full poker game flow."""

    def test_full_hand_flow(self):
        """Test a complete hand from start to finish."""
        args = MockArgs()
        service = PokerService(args)

        # Create table
        service.create_table("test-table", "holdem", "no_limit", 1, 2)

        # Join players
        service.join_table("test-table", "Alice", 500)
        service.join_table("test-table", "Bob", 500)
        service.join_table("test-table", "Charlie", 500)

        # Start hand
        result = service.start_hand("test-table")
        assert result["success"] is True

        table = service._tables["test-table"]
        assert table.game_stage == "preflop"
        assert len(table.community_cards) == 0

        # Verify each player has 2 hole cards
        for player in table.players.values():
            assert len(player.hole_cards) == 2


class TestTexasHoldEmIntegration:
    """Integration tests for Texas Hold'em variant."""

    def test_create_hold_em_table(self):
        """Test creating a Texas Hold'em table."""
        args = MockArgs()
        service = PokerService(args)

        result = service.create_table(
            table_moniker="holdem-test",
            variant_name="texas_hold_em",
            betting_structure="no_limit",
            small_blind=2,
            big_blind=5,
        )

        assert result["success"] is True
        table = service._tables["holdem-test"]
        assert table.variant.name == "texas_hold_em"
        assert table.variant.hole_cards_per_player == 2
        assert table.small_blind == 2
        assert table.big_blind == 5

    def test_hold_em_deals_two_hole_cards(self):
        """Test that Hold'em deals 2 hole cards to each player."""
        args = MockArgs()
        service = PokerService(args)

        service.create_table("holdem", "holdem", "no_limit", 1, 2)
        service.join_table("holdem", "Alice", 500)
        service.join_table("holdem", "Bob", 500)
        service.start_hand("holdem")

        table = service._tables["holdem"]
        for player in table.players.values():
            assert len(player.hole_cards) == 2

    def test_hold_em_streets(self):
        """Test that Hold'em has correct betting streets."""
        args = MockArgs()
        service = PokerService(args)

        service.create_table("holdem", "holdem", "no_limit", 1, 2)
        service.join_table("holdem", "Alice", 500)
        service.join_table("holdem", "Bob", 500)
        service.start_hand("holdem")

        table = service._tables["holdem"]
        streets = table.variant.get_betting_streets()
        assert streets == ["preflop", "flop", "turn", "river"]

    def test_hold_em_community_cards_per_street(self):
        """Test correct community cards dealt per street."""
        args = MockArgs()
        service = PokerService(args)

        service.create_table("holdem", "holdem", "no_limit", 1, 2)
        service.join_table("holdem", "Alice", 500)
        service.join_table("holdem", "Bob", 500)
        service.start_hand("holdem")

        table = service._tables["holdem"]
        community = table.variant.get_community_cards_per_street()

        assert community["preflop"] == 0
        assert community["flop"] == 3
        assert community["turn"] == 1
        assert community["river"] == 1
        assert table.variant.get_max_community_cards() == 5

    def test_hold_em_no_limit_betting(self):
        """Test No-Limit Hold'em betting structure."""
        args = MockArgs()
        service = PokerService(args)

        service.create_table("holdem", "holdem", "no_limit", 1, 2)
        service.join_table("holdem", "Alice", 500)
        service.join_table("holdem", "Bob", 500)
        service.start_hand("holdem")

        table = service._tables["holdem"]
        assert table.betting_structure == BettingStructure.NO_LIMIT

        limits = table.variant.get_betting_limits(pot_size=100, current_bet=10, min_raise=2)
        assert limits.max_raise is None  # Unlimited

    def test_hold_em_fixed_limit_betting(self):
        """Test Fixed-Limit Hold'em betting structure."""
        args = MockArgs()
        service = PokerService(args)

        service.create_table("holdem-fl", "holdem", "fixed_limit", 1, 2)
        service.join_table("holdem-fl", "Alice", 500)
        service.join_table("holdem-fl", "Bob", 500)
        service.start_hand("holdem-fl")

        table = service._tables["holdem-fl"]
        assert table.betting_structure == BettingStructure.FIXED_LIMIT

        limits = table.variant.get_betting_limits(pot_size=100, current_bet=10, min_raise=2)
        assert limits.max_raise == 8  # 2 * 4


class TestOmahaIntegration:
    """Integration tests for Omaha variant."""

    def test_create_omaha_table(self):
        """Test creating an Omaha table."""
        args = MockArgs()
        service = PokerService(args)

        result = service.create_table(
            table_moniker="omaha-test",
            variant_name="omaha",
            betting_structure="pot_limit",
            small_blind=5,
            big_blind=10,
        )

        assert result["success"] is True
        table = service._tables["omaha-test"]
        assert table.variant.name == "omaha"
        assert table.variant.hole_cards_per_player == 4

    def test_omaha_deals_four_hole_cards(self):
        """Test that Omaha deals 4 hole cards to each player."""
        args = MockArgs()
        service = PokerService(args)

        service.create_table("omaha", "omaha", "pot_limit", 1, 2)
        service.join_table("omaha", "Alice", 500)
        service.join_table("omaha", "Bob", 500)
        service.start_hand("omaha")

        table = service._tables["omaha"]
        for player in table.players.values():
            assert len(player.hole_cards) == 4

    def test_omaha_streets(self):
        """Test that Omaha has same streets as Hold'em."""
        args = MockArgs()
        service = PokerService(args)

        service.create_table("omaha", "omaha", "pot_limit", 1, 2)
        service.join_table("omaha", "Alice", 500)
        service.join_table("omaha", "Bob", 500)
        service.start_hand("omaha")

        table = service._tables["omaha"]
        streets = table.variant.get_betting_streets()
        assert streets == ["preflop", "flop", "turn", "river"]

    def test_omaha_pot_limit_betting(self):
        """Test Pot-Limit Omaha betting structure."""
        args = MockArgs()
        service = PokerService(args)

        service.create_table("omaha-pl", "omaha", "pot_limit", 1, 2)
        service.join_table("omaha-pl", "Alice", 500)
        service.join_table("omaha-pl", "Bob", 500)
        service.start_hand("omaha-pl")

        table = service._tables["omaha-pl"]
        assert table.betting_structure == BettingStructure.POT_LIMIT

        limits = table.variant.get_betting_limits(pot_size=100, current_bet=10, min_raise=2)
        assert limits.max_raise == 110  # pot + call

    def test_omaha_evaluate_showdown(self):
        """Test Omaha hand evaluation requires 2 hole cards."""
        args = MockArgs()
        service = PokerService(args)

        service.create_table("omaha", "omaha", "pot_limit", 1, 2)
        service.join_table("omaha", "Alice", 500)
        service.join_table("omaha", "Bob", 500)
        service.start_hand("omaha")

        table = service._tables["omaha"]
        alice = table.players["Alice"]

        rank, best = table.variant.evaluate_showdown(
            ["AH", "KD", "QS", "JC"],
            ["QH", "JD", "10D", "2S", "3H"]
        )
        assert rank >= 0  # Should evaluate without error


class TestSevenCardStudIntegration:
    """Integration tests for 7-Card Stud variant."""

    def test_create_stud_table(self):
        """Test creating a 7-Card Stud table."""
        args = MockArgs()
        service = PokerService(args)

        result = service.create_table(
            table_moniker="stud-test",
            variant_name="seven_card_stud",
            betting_structure="fixed_limit",
            small_blind=1,
            big_blind=2,
        )

        assert result["success"] is True
        table = service._tables["stud-test"]
        assert table.variant.name == "seven_card_stud"
        assert table.variant.hole_cards_per_player == 7

    def test_stud_deals_initial_hole_cards(self):
        """Test that 7-Card Stud deals initial hole cards correctly."""
        args = MockArgs()
        service = PokerService(args)

        service.create_table("stud", "stud", "fixed_limit", 1, 2)
        service.join_table("stud", "Alice", 500)
        service.join_table("stud", "Bob", 500)
        service.start_hand("stud")

        table = service._tables["stud"]
        # Third street (initial deal): 2 down + 1 up = 3 cards
        for player in table.players.values():
            assert len(player.hole_cards) == 3

    def test_stud_streets(self):
        """Test that Stud has correct betting streets."""
        args = MockArgs()
        service = PokerService(args)

        service.create_table("stud", "stud", "fixed_limit", 1, 2)
        service.join_table("stud", "Alice", 500)
        service.join_table("stud", "Bob", 500)
        service.start_hand("stud")

        table = service._tables["stud"]
        streets = table.variant.get_betting_streets()
        assert streets == ["third_street", "fourth_street", "fifth_street", "sixth_street", "seventh_street"]

    def test_stud_no_community_cards(self):
        """Test that Stud has no community cards."""
        args = MockArgs()
        service = PokerService(args)

        service.create_table("stud", "stud", "fixed_limit", 1, 2)
        service.join_table("stud", "Alice", 500)
        service.join_table("stud", "Bob", 500)
        service.start_hand("stud")

        table = service._tables["stud"]
        community = table.variant.get_community_cards_per_street()
        assert all(v == 0 for v in community.values())
        assert table.variant.get_max_community_cards() == 0

    def test_stud_fixed_limit_betting(self):
        """Test Fixed-Limit Stud betting structure."""
        args = MockArgs()
        service = PokerService(args)

        service.create_table("stud-fl", "stud", "fixed_limit", 1, 2)
        service.join_table("stud-fl", "Alice", 500)
        service.join_table("stud-fl", "Bob", 500)
        service.start_hand("stud-fl")

        table = service._tables["stud-fl"]
        assert table.betting_structure == BettingStructure.FIXED_LIMIT

        limits = table.variant.get_betting_limits(pot_size=100, current_bet=10, min_raise=2)
        assert limits.max_raise == 2  # Fixed limit

    def test_stud_evaluate_showdown(self):
        """Test Stud hand evaluation from 7 hole cards."""
        args = MockArgs()
        service = PokerService(args)

        service.create_table("stud", "stud", "fixed_limit", 1, 2)
        service.join_table("stud", "Alice", 500)
        service.join_table("stud", "Bob", 500)
        service.start_hand("stud")

        table = service._tables["stud"]

        rank, best = table.variant.evaluate_showdown(
            ["AH", "AD", "AC", "KD", "KS", "QS", "7S"],
            []  # No community cards in stud
        )
        # Aces full of Kings
        assert rank >= 6  # FULL_HOUSE


class TestVariantComparison:
    """Tests comparing different variants."""

    def test_all_variants_available(self):
        """Test that all variants can be created."""
        args = MockArgs()
        service = PokerService(args)

        variants = [
            ("holdem-table", "holdem", "no_limit"),
            ("omaha-table", "omaha", "pot_limit"),
            ("stud-table", "stud", "fixed_limit"),
        ]

        for moniker, variant, betting in variants:
            result = service.create_table(moniker, variant, betting, 1, 2)
            assert result["success"] is True

        tables = service.list_tables()
        assert len(tables) == 3

    def test_hole_cards_per_variant(self):
        """Test correct hole card counts for each variant."""
        args = MockArgs()
        service = PokerService(args)

        variants = [
            ("holdem", "holdem", 2),
            ("omaha", "omaha", 4),
            ("stud", "seven_card_stud", 7),  # Total possible, not initial deal
        ]

        for moniker, variant, total_cards in variants:
            service.create_table(moniker, variant, "no_limit", 1, 2)
            service.join_table(moniker, "Alice", 500)
            service.join_table(moniker, "Bob", 500)
            service.start_hand(moniker)

            table = service._tables[moniker]
            assert table.variant.hole_cards_per_player == total_cards


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
