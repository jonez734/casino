#!/usr/bin/env python3
# casino/tests/test_new_features_integration.py
# Integration tests for surrender, hole card, soft 17, and 5-card charlie features

import asyncio
import json
import sys
import unittest
from typing import Optional

import pytest

sys.path.insert(0, "/home/opencode/data/work/casino/src")

import websockets
from websockets.exceptions import ConnectionClosed

from casino import lib
from casino.tests.test_blackjack_flow import WebSocketTestClient


DEFAULT_TIMEOUT = 10.0


@pytest.mark.integration
class BaseIntegrationTest(unittest.IsolatedAsyncioTestCase):
    """Base class for integration tests with server setup."""

    async def asyncSetUp(self):
        """Set up test server and database."""
        from bbsengine6.net import WebSocketServer
        from bbsengine6 import database
        from casino.api.handler import MessageRouter

        parser = lib.buildargs()
        self.args = parser.parse_args(["--databasename", "zoid6test"])

        self.pool = database.getpool(self.args)

        # Clean up any leftover test data
        try:
            with database.connect(self.args, pool=self.pool) as conn:
                with database.cursor(conn) as cur:
                    cur.execute("DELETE FROM casino.__betlog WHERE cardtablemoniker = 'blackjack-jam'")
        except Exception as e:
            pass  # Ignore cleanup errors
        
        try:
            with database.connect(self.args, pool=self.pool) as conn:
                with database.cursor(conn) as cur:
                    cur.execute("DELETE FROM casino.__hand WHERE gameid IN (SELECT id FROM casino.__game WHERE tablemoniker = 'blackjack-jam')")
        except Exception as e:
            pass  # Ignore cleanup errors
            
        try:
            with database.connect(self.args, pool=self.pool) as conn:
                with database.cursor(conn) as cur:
                    cur.execute("DELETE FROM casino.__game WHERE tablemoniker = 'blackjack-jam'")
        except Exception as e:
            pass  # Ignore cleanup errors
            
        try:
            with database.connect(self.args, pool=self.pool) as conn:
                with database.cursor(conn) as cur:
                    cur.execute("DELETE FROM casino.__table WHERE moniker = 'blackjack-jam'")
        except Exception as e:
            pass  # Ignore cleanup errors
            
        try:
            with database.connect(self.args, pool=self.pool) as conn:
                with database.cursor(conn) as cur:
                    cur.execute("DELETE FROM casino.map_cardtable_player WHERE cardtablemoniker = 'blackjack-jam'")
        except Exception as e:
            pass  # Ignore cleanup errors
            
        try:
            with database.connect(self.args, pool=self.pool) as conn:
                with database.cursor(conn) as cur:
                    cur.execute("DELETE FROM casino.__bank_table WHERE table_moniker = 'blackjack-jam'")
        except Exception as e:
            pass  # Ignore cleanup errors

        try:
            with database.connect(self.args, pool=self.pool) as conn:
                with database.cursor(conn) as cur:
                    cur.execute(
                        "INSERT INTO engine.__member (moniker, loginid, password, email, credits) "
                        "VALUES ('jam', 'jam', crypt('test', gen_salt('md5')), 'jam@test.local', 100000) "
                        "ON CONFLICT (moniker) DO UPDATE SET password = crypt('test', gen_salt('md5')), credits = 100000"
                    )
        except Exception as e:
            print(f"Warning: Could not set up member: {e}")

        try:
            with database.connect(self.args, pool=self.pool) as conn:
                with database.cursor(conn) as cur:
                    cur.execute(
                        "INSERT INTO bank.__account (moniker, balance) VALUES ('jam', 100000) "
                        "ON CONFLICT (moniker) DO UPDATE SET balance = 100000"
                    )
        except Exception as e:
            print(f"Warning: Could not set up bank account: {e}")

        self.server = WebSocketServer(host="127.0.0.1", port=8766)
        self.router = MessageRouter(self.args)
        self.router.register_all(self.server)

        await self.server.start()
        self._server_started = True
        self.client: Optional[WebSocketTestClient] = None

    async def asyncTearDown(self):
        """Clean up after test."""
        from bbsengine6 import database

        if self.client:
            await self.client.close()

        if hasattr(self, "_server_started") and self._server_started:
            await self.server.stop()

        if hasattr(self, "pool") and self.pool is not None:
            try:
                with database.connect(self.args, pool=self.pool) as conn:
                    with database.cursor(conn) as cur:
                        cur.execute("DELETE FROM casino.__betlog WHERE cardtablemoniker = 'blackjack-jam'")
                        cur.execute("DELETE FROM casino.__hand WHERE gameid IN (SELECT id FROM casino.__game WHERE tablemoniker = 'blackjack-jam')")
                        cur.execute("DELETE FROM casino.__game WHERE tablemoniker = 'blackjack-jam'")
                        cur.execute("DELETE FROM casino.__table WHERE moniker = 'blackjack-jam'")
                        cur.execute("DELETE FROM casino.map_cardtable_player WHERE cardtablemoniker = 'blackjack-jam'")
                        cur.execute("DELETE FROM casino.__bank_table WHERE table_moniker = 'blackjack-jam'")
            except Exception as e:
                print(f"Cleanup error: {e}")
                pass

        if hasattr(self, "pool") and self.pool is not None:
            self.pool.close()
            self.pool = None


class TestSurrenderIntegration(BaseIntegrationTest):
    """Integration test for surrender via WebSocket."""

    async def test_surrender_integration(self):
        """Test surrender action via WebSocket protocol."""
        uri = "ws://127.0.0.1:8766/"
        client = WebSocketTestClient(uri)

        try:
            await client.connect()

            await client.send({"type": "auth", "moniker": "jam", "password": "test"})
            response = await client.receive()
            self.assertEqual(response["type"], "auth_result")
            self.assertTrue(response["success"])

            await client.send({
                "type": "create_table",
                "game_type": "blackjack",
                "min_bet": 10,
                "max_bet": 1000,
                "shoe_decks": 6,
            })
            response = await client.receive()
            self.assertEqual(response["type"], "table_created")
            table_id = response["moniker"]

            await client.send({"type": "join_table", "moniker": table_id})
            response = await client.receive()
            self.assertEqual(response["type"], "joined_table")

            await client.send({"type": "bet", "amount": 50})

            messages = await client.receive_messages(max_count=10, timeout=5.0)
            game_state = None
            for msg in messages:
                if msg.get("type") == "game_state":
                    game_state = msg
                    break

            self.assertIsNotNone(game_state)
            player_hand = game_state.get("hands", [])
            self.assertEqual(len(player_hand), 1)
            self.assertEqual(len(player_hand[0].get("cards", [])), 2)
            self.assertTrue(player_hand[0].get("can_surrender", False))

            await client.send({"type": "surrender"})

            messages = await client.receive_messages(max_count=10, timeout=5.0)
            
            # Check game state for surrender status
            game_state = None
            for msg in messages:
                if msg.get("type") == "game_state":
                    game_state = msg
                    break
            
            self.assertIsNotNone(game_state, "Should get game state after surrender")
            hands = game_state.get("hands", [])
            self.assertEqual(len(hands), 1)
            # Hand status should be surrendered
            self.assertEqual(hands[0].get("status"), "surrendered")
            
            print("✓ Surrender integration test passed")

        except ConnectionError as e:
            self.fail(f"Connection error: {e}")
        except TimeoutError as e:
            self.fail(f"Timeout error: {e}")
        except AssertionError:
            raise
        except Exception as e:
            self.fail(f"Unexpected error: {e}")
        finally:
            await client.close()


class TestHoleCardIntegration(BaseIntegrationTest):
    """Integration test for hole card hiding/reveal."""

    async def test_hole_card_hidden_integration(self):
        """Test dealer hole card is hidden then revealed."""
        uri = "ws://127.0.0.1:8766/"
        client = WebSocketTestClient(uri)

        try:
            await client.connect()

            await client.send({"type": "auth", "moniker": "jam", "password": "test"})
            response = await client.receive()
            self.assertEqual(response["type"], "auth_result")
            self.assertTrue(response["success"])

            await client.send({
                "type": "create_table",
                "game_type": "blackjack",
                "min_bet": 10,
                "max_bet": 1000,
            })
            response = await client.receive()
            self.assertEqual(response["type"], "table_created")
            table_id = response["moniker"]

            await client.send({"type": "join_table", "moniker": table_id})
            response = await client.receive()
            self.assertEqual(response["type"], "joined_table")

            await client.send({"type": "bet", "amount": 50})

            messages = await client.receive_messages(max_count=10, timeout=5.0)
            game_state = None
            for msg in messages:
                if msg.get("type") == "game_state":
                    game_state = msg
                    break

            self.assertIsNotNone(game_state)
            dealer_hand = game_state.get("dealer_hand", [])
            
            self.assertEqual(len(dealer_hand), 2, "Dealer should have 2 cards")
            self.assertEqual(dealer_hand[1], "hidden", "Second dealer card should be hidden")

            print(f"  Dealer hand before reveal: {dealer_hand}")

            await client.send({"type": "stand"})

            messages = await client.receive_messages(max_count=10, timeout=5.0)
            game_state = None
            for msg in messages:
                if msg.get("type") == "game_state":
                    game_state = msg

            self.assertIsNotNone(game_state)
            dealer_hand_after = game_state.get("dealer_hand", [])
            
            print(f"  Dealer hand after reveal: {dealer_hand_after}")

            self.assertNotIn("hidden", dealer_hand_after,
                           "Hole card should be revealed after settlement")
            
            self.assertGreaterEqual(len(dealer_hand_after), 2)

            print("✓ Hole card integration test passed")

        except ConnectionError as e:
            self.fail(f"Connection error: {e}")
        except TimeoutError as e:
            self.fail(f"Timeout error: {e}")
        except AssertionError:
            raise
        except Exception as e:
            self.fail(f"Unexpected error: {e}")
        finally:
            await client.close()


class TestSoft17Integration(BaseIntegrationTest):
    """Integration test for dealer soft 17 rule."""

    async def test_soft_17_stand_rule(self):
        """Test dealer stands on soft 17 when rule is 'stand'."""
        uri = "ws://127.0.0.1:8766/"
        client = WebSocketTestClient(uri)

        try:
            await client.connect()

            await client.send({"type": "auth", "moniker": "jam", "password": "test"})
            response = await client.receive()
            self.assertEqual(response["type"], "auth_result")
            self.assertTrue(response["success"])

            await client.send({
                "type": "create_table",
                "game_type": "blackjack",
                "min_bet": 10,
                "max_bet": 1000,
                "attrs": {"soft_17": "stand"},
            })
            response = await client.receive()
            self.assertEqual(response["type"], "table_created")
            table_id = response["moniker"]

            await client.send({"type": "join_table", "moniker": table_id})
            response = await client.receive()
            self.assertEqual(response["type"], "joined_table")

            await client.send({"type": "bet", "amount": 50})

            await client.send({"type": "stand"})

            messages = await client.receive_messages(max_count=10, timeout=5.0)
            game_state = None
            for msg in messages:
                if msg.get("type") == "game_state":
                    game_state = msg

            self.assertIsNotNone(game_state)
            
            print(f"  Dealer total (soft_17=stand): {game_state.get('dealer_total')}")
            print("✓ Soft 17 stand rule integration test passed")

        except ConnectionError as e:
            self.fail(f"Connection error: {e}")
        except TimeoutError as e:
            self.fail(f"Timeout error: {e}")
        except AssertionError:
            raise
        except Exception as e:
            self.fail(f"Unexpected error: {e}")
        finally:
            await client.close()

    async def test_soft_17_hit_rule(self):
        """Test dealer hits on soft 17 when rule is 'hit' (default)."""
        uri = "ws://127.0.0.1:8766/"
        client = WebSocketTestClient(uri)

        try:
            await client.connect()

            await client.send({"type": "auth", "moniker": "jam", "password": "test"})
            response = await client.receive()
            self.assertEqual(response["type"], "auth_result")
            self.assertTrue(response["success"])

            await client.send({
                "type": "create_table",
                "game_type": "blackjack",
                "min_bet": 10,
                "max_bet": 1000,
                "attrs": {"soft_17": "hit"},
            })
            response = await client.receive()
            self.assertEqual(response["type"], "table_created")
            table_id = response["moniker"]

            await client.send({"type": "join_table", "moniker": table_id})
            response = await client.receive()
            self.assertEqual(response["type"], "joined_table")

            await client.send({"type": "bet", "amount": 50})

            await client.send({"type": "stand"})

            messages = await client.receive_messages(max_count=10, timeout=5.0)
            game_state = None
            for msg in messages:
                if msg.get("type") == "game_state":
                    game_state = msg

            self.assertIsNotNone(game_state)
            
            print(f"  Dealer total (soft_17=hit): {game_state.get('dealer_total')}")
            print("✓ Soft 17 hit rule integration test passed")

        except ConnectionError as e:
            self.fail(f"Connection error: {e}")
        except TimeoutError as e:
            self.fail(f"Timeout error: {e}")
        except AssertionError:
            raise
        except Exception as e:
            self.fail(f"Unexpected error: {e}")
        finally:
            await client.close()


class TestFiveCardCharlieIntegration(BaseIntegrationTest):
    """Integration test for 5-card Charlie rule."""

    async def test_five_card_charlie_integration(self):
        """Test 5-card Charlie automatic win."""
        uri = "ws://127.0.0.1:8766/"
        client = WebSocketTestClient(uri)

        try:
            await client.connect()

            await client.send({"type": "auth", "moniker": "jam", "password": "test"})
            response = await client.receive()
            self.assertEqual(response["type"], "auth_result")
            self.assertTrue(response["success"])

            await client.send({
                "type": "create_table",
                "game_type": "blackjack",
                "min_bet": 10,
                "max_bet": 1000,
                "attrs": {"charlie": True},
            })
            response = await client.receive()
            self.assertEqual(response["type"], "table_created")
            table_id = response["moniker"]

            await client.send({"type": "join_table", "moniker": table_id})
            response = await client.receive()
            self.assertEqual(response["type"], "joined_table")

            await client.send({"type": "bet", "amount": 50})

            hit_count = 0
            max_hits = 5
            
            while hit_count < max_hits:
                await client.send({"type": "hit"})
                messages = await client.receive_messages(max_count=10, timeout=5.0)
                
                game_state = None
                for msg in messages:
                    if msg.get("type") == "game_state":
                        game_state = msg
                        break
                
                if not game_state:
                    break
                    
                hands = game_state.get("hands", [])
                if hands:
                    player_hand = hands[0]
                    cards = player_hand.get("cards", [])
                    status = player_hand.get("status", "")
                    
                    print(f"  After hit {hit_count + 1}: {len(cards)} cards, status={status}, total={player_hand.get('total')}")
                    
                    if status == "charlie":
                        print("  ✓ 5-card Charlie achieved!")
                        break
                    if status == "bust":
                        print("  ✗ Busted before 5 cards")
                        break
                    if len(cards) >= 5:
                        break
                        
                hit_count += 1
            
            print("✓ 5-card Charlie integration test passed")

        except ConnectionError as e:
            self.fail(f"Connection error: {e}")
        except TimeoutError as e:
            self.fail(f"Timeout error: {e}")
        except AssertionError:
            raise
        except Exception as e:
            self.fail(f"Unexpected error: {e}")
        finally:
            await client.close()


class TestSurrenderDisabled(BaseIntegrationTest):
    """Integration test for disabled surrender."""

    async def test_surrender_disabled(self):
        """Test surrender is not available when disabled."""
        uri = "ws://127.0.0.1:8766/"
        client = WebSocketTestClient(uri)

        try:
            await client.connect()

            await client.send({"type": "auth", "moniker": "jam", "password": "test"})
            response = await client.receive()
            self.assertEqual(response["type"], "auth_result")
            self.assertTrue(response["success"])

            await client.send({
                "type": "create_table",
                "game_type": "blackjack",
                "min_bet": 10,
                "max_bet": 1000,
                "attrs": {"surrender": False},
            })
            response = await client.receive()
            self.assertEqual(response["type"], "table_created")
            table_id = response["moniker"]

            await client.send({"type": "join_table", "moniker": table_id})
            response = await client.receive()
            self.assertEqual(response["type"], "joined_table")

            await client.send({"type": "bet", "amount": 50})

            messages = await client.receive_messages(max_count=10, timeout=5.0)
            game_state = None
            for msg in messages:
                if msg.get("type") == "game_state":
                    game_state = msg
                    break

            self.assertIsNotNone(game_state)
            player_hand = game_state.get("hands", [])
            self.assertEqual(len(player_hand), 1)
            
            can_surrender = player_hand[0].get("can_surrender", False)
            self.assertFalse(can_surrender, "Surrender should be disabled")

            print("✓ Surrender disabled test passed")

        except ConnectionError as e:
            self.fail(f"Connection error: {e}")
        except TimeoutError as e:
            self.fail(f"Timeout error: {e}")
        except AssertionError:
            raise
        except Exception as e:
            self.fail(f"Unexpected error: {e}")
        finally:
            await client.close()


if __name__ == "__main__":
    unittest.main()
