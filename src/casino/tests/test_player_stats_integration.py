#!/usr/bin/env python3
# casino/tests/test_player_stats_integration.py
# Integration tests for player statistics tracking

import asyncio
import sys
import unittest

sys.path.insert(0, "/home/opencode/data/work/casino/src")

from bbsengine6 import database
from casino import lib
from casino.dal import player as dal_player


def stats_column_exists(args):
    """Check if the stats column exists in __player table."""
    try:
        with database.connect(args) as conn:
            with database.cursor(conn) as cur:
                cur.execute(
                    "SELECT 1 FROM information_schema.columns WHERE table_name = '__player' AND column_name = 'stats'"
                )
                return cur.fetchone() is not None
    except Exception:
        return False


class TestPlayerStatsDALIntegration(unittest.IsolatedAsyncioTestCase):
    """Integration tests for player stats DAL functions."""

    async def asyncSetUp(self):
        """Set up test database and player."""
        parser = lib.buildargs()
        self.args = parser.parse_args(["--databasename", "zoid6test"])
        self.pool = database.getpool(self.args)
        self.test_moniker = "stats_test_player"
        
        self.stats_column_available = stats_column_exists(self.args)
        
        if not self.stats_column_available:
            self.skipTest("stats column not available in database - run migration first")

        try:
            with database.connect(self.args, pool=self.pool) as conn:
                with database.cursor(conn) as cur:
                    cur.execute(
                        "INSERT INTO engine.__member (moniker, loginid, password, email, credits) "
                        "VALUES ('stats_test_player', 'stats_test_player', crypt('test', gen_salt('md5')), 'stats@test.local', 100000) "
                        "ON CONFLICT (moniker) DO UPDATE SET password = crypt('test', gen_salt('md5'))"
                    )
        except Exception as e:
            pass

        try:
            with database.connect(self.args, pool=self.pool) as conn:
                with database.cursor(conn) as cur:
                    cur.execute(
                        "DELETE FROM casino.__player WHERE membermoniker = 'stats_test_player'"
                    )
        except Exception as e:
            pass

        dal_player.get_or_create_player(self.args, self.test_moniker)

    async def asyncTearDown(self):
        """Clean up test data."""
        if hasattr(self, "pool") and self.pool is not None:
            try:
                with database.connect(self.args, pool=self.pool) as conn:
                    with database.cursor(conn) as cur:
                        cur.execute(
                            "DELETE FROM casino.__player WHERE membermoniker = 'stats_test_player'"
                        )
            except Exception:
                pass
            self.pool.close()
            self.pool = None

    async def test_get_player_stats_initial_empty(self):
        """New player should have empty stats."""
        stats = dal_player.get_player_stats(self.args, self.test_moniker)
        self.assertEqual(stats, {})

    async def test_increment_stat_single(self):
        """Can increment a single stat."""
        dal_player.increment_stat(self.args, self.test_moniker, "wins", 1)
        stats = dal_player.get_player_stats(self.args, self.test_moniker)
        self.assertEqual(stats.get("wins"), 1)

    async def test_increment_stat_multiple(self):
        """Can increment same stat multiple times."""
        dal_player.increment_stat(self.args, self.test_moniker, "wins", 1)
        dal_player.increment_stat(self.args, self.test_moniker, "wins", 1)
        dal_player.increment_stat(self.args, self.test_moniker, "wins", 1)
        stats = dal_player.get_player_stats(self.args, self.test_moniker)
        self.assertEqual(stats.get("wins"), 3)

    async def test_increment_stat_multiple_stats(self):
        """Can increment multiple different stats."""
        dal_player.increment_stat(self.args, self.test_moniker, "wins", 1)
        dal_player.increment_stat(self.args, self.test_moniker, "losses", 1)
        dal_player.increment_stat(self.args, self.test_moniker, "pushes", 1)
        dal_player.increment_stat(self.args, self.test_moniker, "net", 100)
        stats = dal_player.get_player_stats(self.args, self.test_moniker)
        self.assertEqual(stats.get("wins"), 1)
        self.assertEqual(stats.get("losses"), 1)
        self.assertEqual(stats.get("pushes"), 1)
        self.assertEqual(stats.get("net"), 100)

    async def test_increment_stat_game_specific(self):
        """Can increment game-specific stats with dot notation."""
        dal_player.increment_stat(self.args, self.test_moniker, "blackjack.blackjacks", 1)
        dal_player.increment_stat(self.args, self.test_moniker, "blackjack.busts", 1)
        dal_player.increment_stat(self.args, self.test_moniker, "blackjack.hands_played", 1)
        dal_player.increment_stat(self.args, self.test_moniker, "blackjack.surrenders", 1)
        stats = dal_player.get_player_stats(self.args, self.test_moniker)
        self.assertEqual(stats.get("blackjack.blackjacks"), 1)
        self.assertEqual(stats.get("blackjack.busts"), 1)
        self.assertEqual(stats.get("blackjack.hands_played"), 1)
        self.assertEqual(stats.get("blackjack.surrenders"), 1)

    async def test_increment_stat_negative_net(self):
        """Can track negative net (losses)."""
        dal_player.increment_stat(self.args, self.test_moniker, "net", -50)
        stats = dal_player.get_player_stats(self.args, self.test_moniker)
        self.assertEqual(stats.get("net"), -50)

    async def test_update_player_stats_full_replace(self):
        """Can replace all stats at once."""
        dal_player.increment_stat(self.args, self.test_moniker, "wins", 5)
        dal_player.update_player_stats(self.args, self.test_moniker, {"wins": 10, "losses": 3})
        stats = dal_player.get_player_stats(self.args, self.test_moniker)
        self.assertEqual(stats.get("wins"), 10)
        self.assertEqual(stats.get("losses"), 3)

    async def test_increment_stat_invalid_name_raises(self):
        """Invalid stat name should raise ValueError."""
        with self.assertRaises(ValueError) as context:
            dal_player.increment_stat(self.args, self.test_moniker, "invalid_stat", 1)
        self.assertIn("Invalid stat name", str(context.exception))

    async def test_increment_stat_invalid_amount_raises(self):
        """Invalid amount (<=0) should raise ValueError."""
        with self.assertRaises(ValueError) as context:
            dal_player.increment_stat(self.args, self.test_moniker, "wins", 0)
        self.assertIn("amount must be a positive integer", str(context.exception))
        
        with self.assertRaises(ValueError) as context:
            dal_player.increment_stat(self.args, self.test_moniker, "wins", -1)
        self.assertIn("amount must be a positive integer", str(context.exception))


if __name__ == "__main__":
    unittest.main()
