"""A dealer natural settles the round on the bet, deterministically.

The natural happens about once in 20 rounds, so the multi-hand tests only hit it some of
the time. This test forces it: the table's shoe is set to a known order, with the dealer
showing an ace and holding a ten, so the peek settles the round on the bet.

The bet's reply must already be settled. A stand after it must find no active game.
"""

import sys
import unittest

import pytest

sys.path.insert(0, "/home/opencode/data/work/casino/src")

from casino.shoe import Shoe
from casino.tests.test_new_features_integration import BaseIntegrationTest
from casino.tests.test_blackjack_flow import WebSocketTestClient

pytestmark = pytest.mark.integration

TABLE = "blackjack-oc_test_natural"
PLAYER = "oc_test_features"


def _forced_shoe(draw_order):
    """A shoe that draws ``draw_order`` in order. ``draw`` pops from the end, so reverse it."""
    return Shoe(cards=list(reversed(draw_order)), decks=1, threshold=1.0)


class TestDealerNatural(BaseIntegrationTest):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        # A game left by an earlier run would be reused by the bet, with its own shoe. Clear
        # this table's rows so the bet deals from the forced shoe.
        from bbsengine6 import database

        with database.connect(self.args, pool=self.pool) as conn, database.cursor(conn) as cur:
            cur.execute(
                "DELETE FROM casino.__hand WHERE gameid IN "
                "(SELECT id FROM casino.__game WHERE tablemoniker = %s)",
                (TABLE,),
            )
            cur.execute("DELETE FROM casino.__game WHERE tablemoniker = %s", (TABLE,))
            cur.execute("DELETE FROM casino.map_cardtable_player WHERE cardtablemoniker = %s", (TABLE,))
            cur.execute("DELETE FROM casino.__bank_table WHERE table_moniker = %s", (TABLE,))
            cur.execute("DELETE FROM casino.__table WHERE moniker = %s", (TABLE,))

    async def test_natural_settles_on_the_bet_and_stand_finds_no_game(self):
        # Draw order: player, player, dealer up (ace), dealer hole (ten): a dealer natural.
        client = WebSocketTestClient(f"ws://127.0.0.1:8766/")
        await client.connect()
        try:
            await client.send({"type": "auth", "moniker": PLAYER, "password": "test"})
            auth = await client.receive()
            self.assertEqual(auth["type"], "auth_result")
            self.assertTrue(auth["success"])

            await client.send({"type": "create_table", "game_type": "blackjack",
                               "min_bet": 10, "max_bet": 1000, "moniker": TABLE})
            await client.receive()
            await client.send({"type": "join_table", "moniker": TABLE})
            await client.receive()

            # A bet is handled by the bet service, which holds its own GameService and its shoes.
            self.router.bet_service.game_service._shoes[TABLE] = _forced_shoe(
                ["9S", "8H", "AD", "KC", "2C", "3C", "4C", "5C", "6C", "7C"]
            )

            await client.send({"type": "bet", "amount": 10})
            messages = await client.receive_messages(max_count=10, timeout=5.0)
            state = next(m for m in messages if m.get("type") == "game_state")
            self.assertEqual(state.get("phase"), "settled",
                             f"a dealer natural must settle the round on the bet; "
                             f"player={state.get('player_hand')} dealer={state.get('dealer_hand')}")
            self.assertNotIn("hidden", state.get("dealer_hand", []),
                             "a settled round reveals the hole card")

            await client.send({"type": "stand"})
            messages = await client.receive_messages(max_count=10, timeout=5.0)
            errors = [m for m in messages if m.get("type") == "error"]
            self.assertTrue(
                any(e.get("message") == "No active game" for e in errors),
                f"a stand after a natural has no game to act on: {messages}",
            )
        finally:
            await client.close()


if __name__ == "__main__":
    unittest.main()
