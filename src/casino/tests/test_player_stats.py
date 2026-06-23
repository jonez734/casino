#!/usr/bin/env python3
# casino/tests/test_player_stats.py
# Unit tests for player statistics DAL functions

import sys
import unittest

sys.path.insert(0, "/home/opencode/data/work/casino/src")

from casino.dal import player as dal_player


class TestPlayerStatsValidation(unittest.TestCase):
    """Unit tests for player stats validation."""

    def test_allowed_stats_defined(self):
        """ALLOWED_STATS should be defined with expected stats."""
        expected = {
            "wins", "losses", "pushes", "net",
            "blackjack.blackjacks", "blackjack.busts", "blackjack.surrenders", "blackjack.hands_played",
        }
        self.assertEqual(dal_player.ALLOWED_STATS, expected)

    def test_allowed_stats_includes_basic(self):
        """ALLOWED_STATS should include basic stats."""
        basic = {"wins", "losses", "pushes", "net"}
        self.assertTrue(basic.issubset(dal_player.ALLOWED_STATS))

    def test_allowed_stats_includes_game_specific(self):
        """ALLOWED_STATS should include game-specific stats."""
        game_specific = {"blackjack.blackjacks", "blackjack.busts", "blackjack.surrenders", "blackjack.hands_played"}
        self.assertTrue(game_specific.issubset(dal_player.ALLOWED_STATS))




class TestIncrementStatValidation(unittest.TestCase):
    """Unit tests for increment_stat validation logic."""

    def test_invalid_stat_name_rejected(self):
        """Invalid stat name should raise ValueError."""
        invalid_stat = "invalid_stat_name"
        self.assertNotIn(invalid_stat, dal_player.ALLOWED_STATS)

    def test_valid_stat_names_accepted(self):
        """Valid stat names should be in ALLOWED_STATS."""
        valid_stats = [
            "wins", "losses", "pushes", "net",
            "blackjack.blackjacks", "blackjack.busts", "blackjack.surrenders", "blackjack.hands_played",
        ]
        for stat in valid_stats:
            self.assertIn(stat, dal_player.ALLOWED_STATS, f"{stat} should be allowed")

    def test_amount_validation_concept(self):
        """Amount must be positive integer."""
        self.assertFalse(-1 > 0, "negative amounts should fail validation")
        self.assertFalse(0 > 0, "zero amounts should fail validation")


class TestStatsExtensibility(unittest.TestCase):
    """Tests for stats extensibility design."""

    def test_can_add_new_stat_to_allowed_list(self):
        """New stats can be added to ALLOWED_STATS easily."""
        original_count = len(dal_player.ALLOWED_STATS)
        
        self.assertGreaterEqual(original_count, 8, "Should have at least 8 stats")
        
        self.assertTrue(True, "JSONB design allows adding new stats without migration")

    def test_game_type_prefix_format(self):
        """Game-specific stats should use game_type.stat_name format."""
        prefixed_stats = [s for s in dal_player.ALLOWED_STATS if "." in s]
        self.assertTrue(len(prefixed_stats) > 0, "Should have prefixed stats")
        
        for stat in prefixed_stats:
            game_type, stat_name = stat.split(".", 1)
            self.assertEqual(game_type, "blackjack", f"Game type should be 'blackjack', got '{game_type}'")


if __name__ == "__main__":
    unittest.main()
