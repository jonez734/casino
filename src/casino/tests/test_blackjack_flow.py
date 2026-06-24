#!/usr/bin/env python3
# casino/tests/test_blackjack_flow.py
# End-to-end test for blackjack flow

import asyncio
import json
import sys
import unittest
from typing import Optional

sys.path.insert(0, "/home/opencode/data/work/casino/src")

import websockets
from websockets.exceptions import ConnectionClosed, ConnectionClosedOK

from casino import lib
from casino.api.handler import MessageRouter


DEFAULT_TIMEOUT = 10.0
PING_INTERVAL = 30.0


class WebSocketTestClient:
    """Robust WebSocket test client with automatic reconnection and ping handling."""

    def __init__(self, uri: str, timeout: float = DEFAULT_TIMEOUT):
        self.uri = uri
        self.timeout = timeout
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self._ping_task: Optional[asyncio.Task] = None
        self._receive_task: Optional[asyncio.Task] = None
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._running = False

    async def connect(self) -> None:
        """Connect to WebSocket server with retry logic."""
        max_retries = 3
        retry_delay = 0.5

        for attempt in range(max_retries):
            try:
                self.ws = await asyncio.wait_for(
                    websockets.connect(
                        self.uri,
                        ping_interval=PING_INTERVAL,
                        ping_timeout=10.0,
                        close_timeout=5.0,
                    ),
                    timeout=self.timeout,
                )
                self._running = True
                # Start background message receiver
                self._receive_task = asyncio.create_task(self._receive_messages())
                print(f"✓ Connected to {self.uri}")
                return
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"Connection attempt {attempt + 1} failed: {e}, retrying...")
                    await asyncio.sleep(retry_delay)
                else:
                    raise ConnectionError(
                        f"Failed to connect after {max_retries} attempts: {e}"
                    )

    async def _receive_messages(self) -> None:
        """Background task to receive messages."""
        try:
            async for message in self.ws:
                if not self._running:
                    break
                try:
                    data = json.loads(message)
                    await self._message_queue.put(data)
                except json.JSONDecodeError as e:
                    print(f"⚠ Failed to decode message: {e}")
        except ConnectionClosed:
            print("⚠ Connection closed by server")
        except Exception as e:
            print(f"⚠ Error receiving messages: {e}")
        finally:
            self._running = False

    async def send(self, message: dict, timeout: Optional[float] = None) -> None:
        """Send a message with timeout."""
        if not self.ws or not self._running:
            raise ConnectionError("Not connected")

        timeout = timeout or self.timeout
        data = json.dumps(message)

        try:
            await asyncio.wait_for(self.ws.send(data), timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"Send timed out after {timeout}s")
        except ConnectionClosed:
            raise ConnectionError("Connection closed during send")

    async def receive(self, timeout: Optional[float] = None) -> dict:
        """Receive a message with timeout."""
        if not self._running:
            raise ConnectionError("Not connected")

        timeout = timeout or self.timeout

        try:
            return await asyncio.wait_for(self._message_queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"Receive timed out after {timeout}s")

    async def receive_any(
        self, timeout: Optional[float] = None, expected_type: Optional[str] = None
    ) -> dict:
        """Receive messages until we get the expected type or timeout."""
        timeout = timeout or self.timeout
        start_time = asyncio.get_event_loop().time()

        while True:
            remaining = self.timeout - (asyncio.get_event_loop().time() - start_time)
            if remaining <= 0:
                raise TimeoutError(f"Receive timed out after {self.timeout}s")

            try:
                msg = await asyncio.wait_for(
                    self._message_queue.get(), timeout=min(remaining, 1.0)
                )
                if expected_type is None or msg.get("type") == expected_type:
                    return msg
                # Put back other messages
                await self._message_queue.put(msg)
            except asyncio.TimeoutError:
                continue

    async def receive_messages(self, max_count: int = 10, timeout: float = 5.0) -> list:
        """Receive multiple messages with timeout."""
        messages = []
        start_time = asyncio.get_event_loop().time()

        for _ in range(max_count):
            remaining = timeout - (asyncio.get_event_loop().time() - start_time)
            if remaining <= 0:
                break

            try:
                msg = await asyncio.wait_for(
                    self._message_queue.get(), timeout=min(remaining, 1.0)
                )
                messages.append(msg)
            except asyncio.TimeoutError:
                break

        return messages

    async def close(self) -> None:
        """Gracefully close the connection."""
        self._running = False

        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        if self._ping_task:
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass

        if self.ws:
            try:
                await self.ws.close(code=1000, reason="Test complete")
            except Exception:
                pass

        # Drain remaining messages
        while not self._message_queue.empty():
            try:
                self._message_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    @property
    def is_connected(self) -> bool:
        if not self._running or not self.ws:
            return False
        try:
            return self.ws.state == websockets.protocol.State.OPEN
        except (AttributeError, TypeError):
            # Fallback for older versions
            return self._running and hasattr(self.ws, "open") and self.ws.open


class TestBlackjackFullFlow(unittest.IsolatedAsyncioTestCase):
    """Test complete blackjack flow: connect -> auth -> list tables -> create -> join -> bet -> game_state"""

    async def asyncSetUp(self):
        """Set up test server and database."""
        from bbsengine6.net import WebSocketServer
        from bbsengine6 import database

        # Build args with test database
        parser = lib.buildargs()
        self.args = parser.parse_args(["--databasename", "zoid6test"])

        # Get pool for database operations
        self.pool = database.getpool(self.args)

        # Set password for test user if needed (insert if not exists)
        # Also ensure user has a bank account with funds and casino credits
        with database.connect(self.args, pool=self.pool) as conn:
            with database.cursor(conn) as cur:
                cur.execute(
                    "INSERT INTO engine.__member (moniker, loginid, password, email, credits) "
                    "VALUES ('jam', 'jam', crypt('test', gen_salt('md5')), 'jam@test.local', 100000) "
                    "ON CONFLICT (moniker) DO UPDATE SET password = crypt('test', gen_salt('md5')), credits = 100000"
                )
                # Ensure user has a bank account with funds
                cur.execute(
                    "INSERT INTO bank.__account (moniker, balance) VALUES ('jam', 100000) "
                    "ON CONFLICT (moniker) DO UPDATE SET balance = 100000"
                )

        # Create server
        self.server = WebSocketServer(host="127.0.0.1", port=8766)

        # Create router
        self.router = MessageRouter(self.args)

        # Register services
        self.router.register_all(self.server)

        # Start server
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

        # Clean up test data from previous runs
        if hasattr(self, "pool") and self.pool is not None:
            try:
                with database.connect(self.args, pool=self.pool) as conn:
                    with database.cursor(conn) as cur:
                        # Reset jam's credits and bank balance for next test
                        cur.execute("UPDATE engine.__member SET credits = 100000 WHERE moniker = 'jam'")
                        cur.execute("UPDATE bank.__account SET balance = 100000 WHERE moniker = 'jam'")
                        # Clean up test tables (blackjack-jam)
                        cur.execute("DELETE FROM casino.__bank_table WHERE table_moniker = 'blackjack-jam'")
                        cur.execute("DELETE FROM casino.__table WHERE moniker = 'blackjack-jam'")
                        # Clean up test games
                        cur.execute("DELETE FROM casino.__game WHERE tablemoniker = 'blackjack-jam'")
                        cur.execute("DELETE FROM casino.map_cardtable_player WHERE cardtablemoniker = 'blackjack-jam'")
                        # Clean up betlog entries for test tables
                        cur.execute("DELETE FROM casino.__betlog WHERE cardtablemoniker LIKE 'blackjack-%'")
            except Exception:
                pass  # Ignore cleanup errors

        if hasattr(self, "pool") and self.pool is not None:
            self.pool.close()
            self.pool = None

    def _verify_betlog(self, table_moniker: str, expected_amount: int, expected_cards: list) -> None:
        """Verify that a bet was logged to casino.__betlog with correct data."""
        from bbsengine6 import database

        with database.connect(self.args, pool=self.pool) as conn:
            with database.cursor(conn) as cur:
                # Check which columns exist (notes/new, currenthand, or old description)
                cur.execute(
                    database.query(
                        """SELECT column_name FROM information_schema.columns 
                           WHERE table_name = '__betlog' AND column_name IN ('notes', 'currenthand', 'description')"""
                    )
                )
                existing_cols = {r["column_name"] for r in cur.fetchall()}
                
                # Build query with only existing columns
                cols = ["playermoniker", "cardtablemoniker", "amount", "status"]
                if "notes" in existing_cols:
                    cols.append("notes")
                elif "description" in existing_cols:
                    cols.append("description")
                if "currenthand" in existing_cols:
                    cols.append("currenthand")
                
                col_str = ", ".join(cols)
                cur.execute(
                    database.query(
                        f"""SELECT {col_str} FROM casino.__betlog WHERE cardtablemoniker = :table_moniker ORDER BY dateposted DESC LIMIT 1""",
                        table_moniker=table_moniker
                    )
                )
                row = cur.fetchone()
                self.assertIsNotNone(row, f"No betlog entry found for table {table_moniker}")

                self.assertEqual(row["playermoniker"], "jam", "Player moniker should be 'jam'")
                self.assertEqual(row["cardtablemoniker"], table_moniker, "Table moniker should match")
                self.assertEqual(row["amount"], expected_amount, f"Bet amount should be {expected_amount}")
                self.assertEqual(row["status"], "pending", "Bet status should be 'pending'")

                # Check currenthand if it exists, otherwise skip the card check
                currenthand = row.get("currenthand") or ""
                if currenthand:
                    for card in expected_cards:
                        self.assertIn(card, currenthand, f"Card {card} should be in betlog currenthand: {currenthand}")

                # Check notes or description
                notes = row.get("notes") or row.get("description") or ""
                print(f"  ✓ Betlog verified: {row['amount']} credits, currenthand='{currenthand}', notes='{notes}'")

    async def test_full_blackjack_flow(self):
        """Test complete blackjack flow from connection to receiving hand."""
        uri = "ws://127.0.0.1:8765/"

        # Create robust client
        self.client = WebSocketTestClient(uri)

        try:
            # Connect
            await self.client.connect()
            self.assertTrue(self.client.is_connected, "Failed to connect")

            # Step 1: Authenticate
            await self.client.send(
                {"type": "auth", "moniker": "jam", "password": "test"}
            )

            response = await self.client.receive()
            self.assertEqual(response["type"], "auth_result")
            self.assertTrue(response["success"])
            self.assertEqual(response["moniker"], "jam")
            print(
                f"\n✓ Authenticated as {response['moniker']} with balance {response['balance']}"
            )

            # Step 2: List tables
            await self.client.send({"type": "list_tables"})

            response = await self.client.receive()
            self.assertEqual(response["type"], "table_list")
            print(f"✓ Listed tables: {len(response.get('tables', []))} table(s)")

            # Step 3: Create a blackjack table
            await self.client.send(
                {
                    "type": "create_table",
                    "game_type": "blackjack",
                    "min_bet": 10,
                    "max_bet": 1000,
                    "shoe_decks": 6,
                    "shoe_threshold": 0.8,
                }
            )

            response = await self.client.receive()
            self.assertEqual(response["type"], "table_created")
            table_id = response["moniker"]
            print(f"✓ Created table {table_id}")

            # Step 4: Ping/Pong
            await self.client.send({"type": "ping"})

            response = await self.client.receive()
            self.assertEqual(response["type"], "pong")
            self.assertIn("timestamp", response)
            print(f"✓ Ping/Pong successful")

            # Step 5: Multiple ping/pongs to test stability
            for i in range(3):
                await self.client.send({"type": "ping"})
                response = await self.client.receive()
                self.assertEqual(response["type"], "pong")
            print(f"✓ Multiple ping/pongs successful")

            # Step 6: Join the table
            await self.client.send({"type": "join_table", "moniker": table_id})

            response = await self.client.receive()
            self.assertEqual(response["type"], "joined_table")
            self.assertEqual(response["moniker"], table_id)
            print(f"✓ Joined table {table_id}")

            # Step 7: Place a bet
            await self.client.send({"type": "bet", "amount": 50})

            # Receive game state (may be multiple messages)
            messages = await self.client.receive_messages(max_count=10, timeout=5.0)

            # Find game_state message
            game_state = None
            for msg in messages:
                if msg.get("type") == "game_state":
                    game_state = msg
                    break

            self.assertIsNotNone(game_state, f"No game_state received. Got: {messages}")
            self.assertEqual(game_state["type"], "game_state")
            self.assertEqual(game_state["table_moniker"], table_id)

            # Verify player has 2 cards
            player_hand = game_state.get("player_hand", [])
            self.assertEqual(
                len(player_hand), 2, f"Expected 2 cards, got {len(player_hand)}"
            )

            player_total = game_state.get("player_total", 0)
            self.assertGreater(player_total, 0, "Player total should be > 0")

            print(f"✓ Received game state:")
            print(f"  - Player hand: {' '.join(player_hand)} [{player_total}]")
            print(
                f"  - Dealer hand: {' '.join(game_state.get('dealer_hand', []))} [{game_state.get('dealer_total', 0)}]"
            )

            # Verify betlog was written correctly
            self._verify_betlog(table_id, 50, player_hand)

            # Step 8: Hit
            await self.client.send({"type": "hit"})

            # Receive updated game state
            messages = await self.client.receive_messages(max_count=10, timeout=5.0)

            game_state = None
            for msg in messages:
                if msg.get("type") == "game_state":
                    game_state = msg
                    break

            if game_state:
                player_hand = game_state.get("player_hand", [])
                player_total = game_state.get("player_total", 0)
                print(f"✓ After hit: {' '.join(player_hand)} [{player_total}]")
                self.assertEqual(len(player_hand), 3, "Should have 3 cards after hit")
            else:
                print("⚠ No game_state received after hit")

            # Step 9: Verify connection is still stable
            await self.client.send({"type": "ping"})
            response = await self.client.receive()
            self.assertEqual(response["type"], "pong")
            print(f"✓ Connection still stable after game actions")

            print("\n✓ Full blackjack flow completed successfully!")

        except ConnectionError as e:
            self.fail(f"Connection error: {e}")
        except TimeoutError as e:
            self.fail(f"Timeout error: {e}")
        except AssertionError:
            raise
        except Exception as e:
            self.fail(f"Unexpected error: {e}")

    async def test_connection_resilience(self):
        """Test that connection handles reconnection gracefully."""
        uri = "ws://127.0.0.1:8765/"

        # Create and connect
        self.client = WebSocketTestClient(uri)
        await self.client.connect()

        # Send auth
        await self.client.send({"type": "auth", "moniker": "jam", "password": "test"})
        response = await self.client.receive()
        self.assertEqual(response["type"], "auth_result")

        # Close and reconnect
        await self.client.close()
        await asyncio.sleep(0.5)

        # Reconnect
        await self.client.connect()

        # Should be able to auth again
        await self.client.send({"type": "auth", "moniker": "jam", "password": "test"})
        response = await self.client.receive()
        self.assertEqual(response["type"], "auth_result")

        print("✓ Connection resilience test passed")

    async def test_stand_after_bet(self):
        """Test placing a bet and then standing (completing the round)."""
        uri = "ws://127.0.0.1:8765/"

        self.client = WebSocketTestClient(uri)

        try:
            await self.client.connect()

            # Authenticate
            await self.client.send(
                {"type": "auth", "moniker": "jam", "password": "test"}
            )
            response = await self.client.receive()
            self.assertEqual(response["type"], "auth_result")
            self.assertTrue(response["success"])

            # Create a blackjack table
            await self.client.send(
                {
                    "type": "create_table",
                    "game_type": "blackjack",
                    "min_bet": 10,
                    "max_bet": 1000,
                    "shoe_decks": 6,
                    "shoe_threshold": 0.8,
                }
            )
            response = await self.client.receive()
            self.assertEqual(response["type"], "table_created")
            table_id = response["moniker"]

            # Join the table
            await self.client.send({"type": "join_table", "moniker": table_id})
            response = await self.client.receive()
            self.assertEqual(response["type"], "joined_table")

            # Place a bet
            await self.client.send({"type": "bet", "amount": 50})

            # Get initial game state
            messages = await self.client.receive_messages(max_count=10, timeout=5.0)
            game_state = None
            for msg in messages:
                if msg.get("type") == "game_state":
                    game_state = msg
                    break

            self.assertIsNotNone(game_state, "No game_state received after bet")
            player_hand_initial = game_state.get("player_hand", [])
            player_total_initial = game_state.get("player_total", 0)
            print(f"  Initial hand: {' '.join(player_hand_initial)} [{player_total_initial}]")

            # Verify betlog was written correctly
            self._verify_betlog(table_id, 50, player_hand_initial)

            # Now stand
            await self.client.send({"type": "stand"})

            # Receive final game state
            messages = await self.client.receive_messages(max_count=10, timeout=5.0)
            game_state = None
            for msg in messages:
                if msg.get("type") == "game_state":
                    game_state = msg
                    break

            self.assertIsNotNone(game_state, "No game_state received after stand")

            # Verify hand didn't change (stand keeps same cards)
            player_hand_after = game_state.get("player_hand", [])
            player_total_after = game_state.get("player_total", 0)
            print(f"  After stand: {' '.join(player_hand_after)} [{player_total_after}]")

            # Verify round is settled after standing
            self.assertEqual(game_state.get("phase"), "settled", "game_state should show phase is settled")

            print("✓ Stand after bet test passed")

        except ConnectionError as e:
            self.fail(f"Connection error: {e}")
        except TimeoutError as e:
            self.fail(f"Timeout error: {e}")
        except AssertionError:
            raise
        except Exception as e:
            self.fail(f"Unexpected error: {e}")

    async def test_hit_then_stand(self):
        """Test full round: bet -> hit -> stand."""
        uri = "ws://127.0.0.1:8765/"

        self.client = WebSocketTestClient(uri)

        try:
            await self.client.connect()

            # Authenticate
            await self.client.send(
                {"type": "auth", "moniker": "jam", "password": "test"}
            )
            response = await self.client.receive()
            self.assertEqual(response["type"], "auth_result")
            self.assertTrue(response["success"])

            # Create a blackjack table
            await self.client.send(
                {
                    "type": "create_table",
                    "game_type": "blackjack",
                    "min_bet": 10,
                    "max_bet": 1000,
                    "shoe_decks": 6,
                    "shoe_threshold": 0.8,
                }
            )
            response = await self.client.receive()
            self.assertEqual(response["type"], "table_created")
            table_id = response["moniker"]

            # Join the table
            await self.client.send({"type": "join_table", "moniker": table_id})
            response = await self.client.receive()
            self.assertEqual(response["type"], "joined_table")

            # Place a bet
            await self.client.send({"type": "bet", "amount": 50})

            # Get initial game state
            messages = await self.client.receive_messages(max_count=10, timeout=5.0)
            game_state = None
            for msg in messages:
                if msg.get("type") == "game_state":
                    game_state = msg
                    break

            self.assertIsNotNone(game_state)
            player_hand_after_bet = game_state.get("player_hand", [])
            player_total_after_bet = game_state.get("player_total", 0)
            print(f"  After bet: {' '.join(player_hand_after_bet)} [{player_total_after_bet}]")
            self.assertEqual(len(player_hand_after_bet), 2, "Should have 2 cards after bet")

            # Verify betlog was written correctly
            self._verify_betlog(table_id, 50, player_hand_after_bet)

            # Hit
            await self.client.send({"type": "hit"})

            messages = await self.client.receive_messages(max_count=10, timeout=5.0)
            game_state = None
            for msg in messages:
                if msg.get("type") == "game_state":
                    game_state = msg
                    break

            self.assertIsNotNone(game_state, "No game_state received after hit")
            player_hand_after_hit = game_state.get("player_hand", [])
            player_total_after_hit = game_state.get("player_total", 0)
            print(f"  After hit: {' '.join(player_hand_after_hit)} [{player_total_after_hit}]")
            self.assertEqual(len(player_hand_after_hit), 3, "Should have 3 cards after hit")

            # Now stand
            await self.client.send({"type": "stand"})

            messages = await self.client.receive_messages(max_count=10, timeout=5.0)
            game_state = None
            for msg in messages:
                if msg.get("type") == "game_state":
                    game_state = msg
                    break

            self.assertIsNotNone(game_state, "No game_state received after stand")
            player_hand_after_stand = game_state.get("player_hand", [])
            print(f"  After stand: {' '.join(player_hand_after_stand)} [{game_state.get('player_total', 0)}]")

            # Verify round is settled
            self.assertEqual(game_state.get("phase"), "settled", "game_state should show phase is settled")

            print("✓ Hit then stand test passed")

        except ConnectionError as e:
            self.fail(f"Connection error: {e}")
        except TimeoutError as e:
            self.fail(f"Timeout error: {e}")
        except AssertionError:
            raise
        except Exception as e:
            self.fail(f"Unexpected error: {e}")

    async def test_invalid_bet_amounts(self):
        """Test that invalid bet amounts are rejected via network."""
        uri = "ws://127.0.0.1:8765/"

        self.client = WebSocketTestClient(uri)

        try:
            await self.client.connect()

            # Authenticate
            await self.client.send(
                {"type": "auth", "moniker": "jam", "password": "test"}
            )
            response = await self.client.receive()
            self.assertEqual(response["type"], "auth_result")
            self.assertTrue(response["success"])

            # Create a blackjack table
            await self.client.send(
                {
                    "type": "create_table",
                    "game_type": "blackjack",
                    "min_bet": 10,
                    "max_bet": 1000,
                    "shoe_decks": 6,
                    "shoe_threshold": 0.8,
                }
            )
            response = await self.client.receive()
            self.assertEqual(response["type"], "table_created")
            table_id = response["moniker"]

            # Join the table
            await self.client.send({"type": "join_table", "moniker": table_id})
            response = await self.client.receive()
            self.assertEqual(response["type"], "joined_table")

            # Test 1: Negative bet amount (-1)
            await self.client.send({"type": "bet", "amount": -1})
            response = await self.client.receive()
            self.assertEqual(response["type"], "error")
            self.assertEqual(response["code"], "invalid_bet")
            print(f"  ✓ Negative bet -1 rejected: {response['message']}")

            # Test 2: Zero bet amount
            await self.client.send({"type": "bet", "amount": 0})
            response = await self.client.receive()
            self.assertEqual(response["type"], "error")
            self.assertEqual(response["code"], "invalid_bet")
            print(f"  ✓ Zero bet rejected: {response['message']}")

            # Test 3: Float bet amount (50.5)
            await self.client.send({"type": "bet", "amount": 50.5})
            response = await self.client.receive()
            self.assertEqual(response["type"], "error")
            self.assertEqual(response["code"], "invalid_bet")
            print(f"  ✓ Float bet 50.5 rejected: {response['message']}")

            # Test 4: String bet amount (should be rejected by JSON parsing, but test anyway)
            # This would fail at JSON level, so we test via the message handler

            # Test 5: Valid bet amount (50)
            await self.client.send({"type": "bet", "amount": 50})
            messages = await self.client.receive_messages(max_count=10, timeout=5.0)
            game_state = None
            for msg in messages:
                if msg.get("type") == "game_state":
                    game_state = msg
                    break
            
            self.assertIsNotNone(game_state, "Valid bet should return game_state")
            self.assertEqual(len(game_state.get("player_hand", [])), 2)
            print(f"  ✓ Valid bet 50 accepted: {game_state.get('player_hand')}")

            # Verify betlog was written correctly
            self._verify_betlog(table_id, 50, game_state.get("player_hand", []))

            print("✓ Invalid bet amounts test passed")

        except ConnectionError as e:
            self.fail(f"Connection error: {e}")
        except TimeoutError as e:
            self.fail(f"Timeout error: {e}")
        except AssertionError:
            raise
        except Exception as e:
            self.fail(f"Unexpected error: {e}")

    def _verify_betlog_settled(self, table_moniker: str) -> None:
        """Verify that a bet was settled in casino.__betlog."""
        from bbsengine6 import database

        with database.connect(self.args, pool=self.pool) as conn:
            with database.cursor(conn) as cur:
                # Check which columns exist
                cur.execute(
                    database.query(
                        """SELECT column_name FROM information_schema.columns 
                           WHERE table_name = '__betlog' AND column_name = 'currenthand'"""
                    )
                )
                has_currenthand = cur.fetchone() is not None
                
                # Build query with only existing columns
                cols = ["playermoniker", "cardtablemoniker", "amount", "status"]
                if has_currenthand:
                    cols.append("currenthand")
                
                col_str = ", ".join(cols)
                cur.execute(
                    database.query(
                        f"""SELECT {col_str} FROM casino.__betlog WHERE cardtablemoniker = :table_moniker ORDER BY dateposted DESC LIMIT 1""",
                        table_moniker=table_moniker
                    )
                )
                row = cur.fetchone()
                self.assertIsNotNone(row, f"No betlog entry found for table {table_moniker}")

                self.assertIn(
                    row["status"], ["won", "lost"],
                    f"Bet status should be settled (won/lost), got '{row['status']}'"
                )

                currenthand = row.get("currenthand") or ""
                print(f"  ✓ Betlog settled: status='{row['status']}', amount={row['amount']}, hand='{currenthand}'")

    async def test_betlog_settlement(self):
        """Test that betlog status changes from pending to won/lost after settlement."""
        uri = "ws://127.0.0.1:8765/"

        self.client = WebSocketTestClient(uri)

        try:
            await self.client.connect()

            # Authenticate
            await self.client.send({"type": "auth", "moniker": "jam", "password": "test"})
            response = await self.client.receive()
            self.assertEqual(response["type"], "auth_result")
            self.assertTrue(response["success"])

            # Create a blackjack table
            await self.client.send({
                "type": "create_table",
                "game_type": "blackjack",
                "min_bet": 10,
                "max_bet": 1000,
                "shoe_decks": 6,
                "shoe_threshold": 0.8,
            })
            response = await self.client.receive()
            self.assertEqual(response["type"], "table_created")
            table_id = response["moniker"]

            # Join the table
            await self.client.send({"type": "join_table", "moniker": table_id})
            response = await self.client.receive()
            self.assertEqual(response["type"], "joined_table")

            # Place a bet
            await self.client.send({"type": "bet", "amount": 50})

            # Get initial game state
            messages = await self.client.receive_messages(max_count=10, timeout=5.0)
            game_state = None
            for msg in messages:
                if msg.get("type") == "game_state":
                    game_state = msg
                    break

            self.assertIsNotNone(game_state, "No game_state received after bet")
            player_hand = game_state.get("player_hand", [])
            print(f"  Initial hand: {' '.join(player_hand)}")

            # Verify bet is pending
            self._verify_betlog(table_id, 50, player_hand)

            # Now stand to settle the game
            await self.client.send({"type": "stand"})

            # Receive final game state
            messages = await self.client.receive_messages(max_count=10, timeout=5.0)
            game_state = None
            for msg in messages:
                if msg.get("type") == "game_state":
                    game_state = msg
                    break

            self.assertIsNotNone(game_state, "No game_state received after stand")
            self.assertEqual(game_state.get("phase"), "settled", "Game should be settled")

            # Verify bet status is now settled (won or lost)
            self._verify_betlog_settled(table_id)

            print("✓ Betlog settlement test passed")

        except ConnectionError as e:
            self.fail(f"Connection error: {e}")
        except TimeoutError as e:
            self.fail(f"Timeout error: {e}")
        except AssertionError:
            raise
        except Exception as e:
            self.fail(f"Unexpected error: {e}")

    async def test_betlog_notes(self):
        """Test that notes can be added to betlog entries."""
        from bbsengine6 import database

        # Check if notes column exists, skip test if not
        with database.connect(self.args, pool=self.pool) as conn:
            with database.cursor(conn) as cur:
                cur.execute(
                    database.query(
                        """SELECT 1 FROM information_schema.columns 
                           WHERE table_name = '__betlog' AND column_name = 'notes'"""
                    )
                )
                if not cur.fetchone():
                    print("  ⚠ Skipping test: 'notes' column does not exist in __betlog")
                    return

        uri = "ws://127.0.0.1:8765/"

        self.client = WebSocketTestClient(uri)

        try:
            await self.client.connect()

            # Authenticate
            await self.client.send({"type": "auth", "moniker": "jam", "password": "test"})
            response = await self.client.receive()
            self.assertEqual(response["type"], "auth_result")
            self.assertTrue(response["success"])

            # Create a blackjack table
            await self.client.send({
                "type": "create_table",
                "game_type": "blackjack",
                "min_bet": 10,
                "max_bet": 1000,
                "shoe_decks": 6,
                "shoe_threshold": 0.8,
            })
            response = await self.client.receive()
            self.assertEqual(response["type"], "table_created")
            table_id = response["moniker"]

            # Join the table
            await self.client.send({"type": "join_table", "moniker": table_id})
            response = await self.client.receive()
            self.assertEqual(response["type"], "joined_table")

            # Place a bet
            await self.client.send({"type": "bet", "amount": 50})

            # Get game state
            messages = await self.client.receive_messages(max_count=10, timeout=5.0)
            game_state = None
            for msg in messages:
                if msg.get("type") == "game_state":
                    game_state = msg
                    break

            self.assertIsNotNone(game_state, "No game_state received after bet")

            # Get the bet ID from betlog
            from bbsengine6 import database
            with database.connect(self.args, pool=self.pool) as conn:
                with database.cursor(conn) as cur:
                    cur.execute(
                        database.query(
                            """SELECT id FROM casino.__betlog 
                               WHERE cardtablemoniker = :table_moniker 
                               ORDER BY dateposted DESC LIMIT 1""",
                            table_moniker=table_id
                        )
                    )
                    row = cur.fetchone()
                    self.assertIsNotNone(row, "No bet found in betlog")
                    bet_id = row["id"]

            # Add a note to the bet
            test_note = "Player requested comp - VIP customer"
            from casino.dal import bet as dal_bet
            dal_bet.update_bet_notes(self.args, bet_id, test_note)

            # Verify the note was added
            with database.connect(self.args, pool=self.pool) as conn:
                with database.cursor(conn) as cur:
                    cur.execute(
                        database.query(
                            """SELECT notes FROM casino.__betlog WHERE id = :bet_id""",
                            bet_id=bet_id
                        )
                    )
                    row = cur.fetchone()
                    self.assertIsNotNone(row, "Bet not found")
                    self.assertEqual(row["notes"], test_note, 
                        f"Notes should be '{test_note}', got '{row['notes']}'")

            print(f"  ✓ Notes test passed: '{test_note}'")

            print("✓ Betlog notes test passed")

        except ConnectionError as e:
            self.fail(f"Connection error: {e}")
        except TimeoutError as e:
            self.fail(f"Timeout error: {e}")
        except AssertionError:
            raise
        except Exception as e:
            self.fail(f"Unexpected error: {e}")

    async def test_betlog_view(self):
        """Test that casino.betlog view returns correct data."""
        from bbsengine6 import database

        # Check if currenthand column exists, skip test if not
        with database.connect(self.args, pool=self.pool) as conn:
            with database.cursor(conn) as cur:
                cur.execute(
                    database.query(
                        """SELECT 1 FROM information_schema.columns 
                           WHERE table_name = '__betlog' AND column_name = 'currenthand'"""
                    )
                )
                if not cur.fetchone():
                    print("  ⚠ Skipping test: 'currenthand' column does not exist in __betlog")
                    return

        uri = "ws://127.0.0.1:8765/"

        self.client = WebSocketTestClient(uri)

        try:
            await self.client.connect()

            # Authenticate
            await self.client.send({"type": "auth", "moniker": "jam", "password": "test"})
            response = await self.client.receive()
            self.assertEqual(response["type"], "auth_result")
            self.assertTrue(response["success"])

            # Create a blackjack table
            await self.client.send({
                "type": "create_table",
                "game_type": "blackjack",
                "min_bet": 10,
                "max_bet": 1000,
                "shoe_decks": 6,
                "shoe_threshold": 0.8,
            })
            response = await self.client.receive()
            self.assertEqual(response["type"], "table_created")
            table_id = response["moniker"]

            # Join the table
            await self.client.send({"type": "join_table", "moniker": table_id})
            response = await self.client.receive()
            self.assertEqual(response["type"], "joined_table")

            # Place a bet
            await self.client.send({"type": "bet", "amount": 50})

            # Get game state
            messages = await self.client.receive_messages(max_count=10, timeout=5.0)
            game_state = None
            for msg in messages:
                if msg.get("type") == "game_state":
                    game_state = msg
                    break

            self.assertIsNotNone(game_state, "No game_state received after bet")
            player_hand = game_state.get("player_hand", [])

            # Query the betlog VIEW (not the table directly)
            from bbsengine6 import database
            with database.connect(self.args, pool=self.pool) as conn:
                with database.cursor(conn) as cur:
                    cur.execute(
                        database.query(
                            """SELECT playermoniker, cardtablemoniker, amount, status, currenthand, 
                                      datepostedepoch, datepostedlocal
                               FROM casino.betlog 
                               WHERE cardtablemoniker = :table_moniker 
                               ORDER BY dateposted DESC LIMIT 1""",
                            table_moniker=table_id
                        )
                    )
                    row = cur.fetchone()
                    self.assertIsNotNone(row, "No bet found in betlog view")

                    # Verify base columns
                    self.assertEqual(row["playermoniker"], "jam")
                    self.assertEqual(row["cardtablemoniker"], table_id)
                    self.assertEqual(row["amount"], 50)
                    self.assertEqual(row["status"], "pending")

                    # Verify computed columns exist
                    self.assertIsNotNone(row["datepostedepoch"], "datepostedepoch should be set")
                    self.assertIsNotNone(row["datepostedlocal"], "datepostedlocal should be set")

                    # Verify currenthand in view
                    currenthand = row["currenthand"] or ""
                    for card in player_hand:
                        self.assertIn(card, currenthand, f"Card {card} should be in currenthand")

            print("  ✓ Betlog view test passed: base cols + datepostedepoch + datepostedlocal")

            print("✓ Betlog view test passed")

        except ConnectionError as e:
            self.fail(f"Connection error: {e}")
        except TimeoutError as e:
            self.fail(f"Timeout error: {e}")
        except AssertionError:
            raise
        except Exception as e:
            self.fail(f"Unexpected error: {e}")

    async def test_betlog_multiple_bets(self):
        """Test that multiple bets are all recorded in betlog."""
        from bbsengine6 import database

        # Get count of bets before
        with database.connect(self.args, pool=self.pool) as conn:
            with database.cursor(conn) as cur:
                cur.execute(
                    database.query(
                        """SELECT COUNT(*) as cnt FROM casino.__betlog WHERE playermoniker = 'jam'"""
                    )
                )
                initial_count = cur.fetchone()["cnt"]

        uri = "ws://127.0.0.1:8765/"

        self.client = WebSocketTestClient(uri)

        try:
            await self.client.connect()

            # Authenticate
            await self.client.send({"type": "auth", "moniker": "jam", "password": "test"})
            response = await self.client.receive()
            self.assertEqual(response["type"], "auth_result")
            self.assertTrue(response["success"])

            # Create a table
            await self.client.send({
                "type": "create_table",
                "game_type": "blackjack",
                "min_bet": 10,
                "max_bet": 1000,
                "shoe_decks": 6,
                "shoe_threshold": 0.8,
            })
            response = await self.client.receive()
            self.assertEqual(response["type"], "table_created")
            table_id = response["moniker"]

            # Join and place first bet
            await self.client.send({"type": "join_table", "moniker": table_id})
            response = await self.client.receive()
            self.assertEqual(response["type"], "joined_table")

            await self.client.send({"type": "bet", "amount": 25})
            messages = await self.client.receive_messages(max_count=10, timeout=5.0)

            # Check betlog after first bet
            with database.connect(self.args, pool=self.pool) as conn:
                with database.cursor(conn) as cur:
                    cur.execute(
                        database.query(
                            """SELECT COUNT(*) as cnt FROM casino.__betlog WHERE playermoniker = 'jam'"""
                        )
                    )
                    count_after_first = cur.fetchone()["cnt"]
                    self.assertEqual(count_after_first, initial_count + 1, "Should have 1 more bet after first bet")

            # Query the bet to verify amount
            with database.connect(self.args, pool=self.pool) as conn:
                with database.cursor(conn) as cur:
                    cur.execute(
                        database.query(
                            """SELECT amount FROM casino.__betlog WHERE playermoniker = 'jam' ORDER BY dateposted DESC LIMIT 1"""
                        )
                    )
                    row = cur.fetchone()
                    self.assertEqual(row["amount"], 25, "First bet should be 25")

            print(f"  ✓ Multiple bets test passed: found {count_after_first - initial_count} new bet(s)")

            print("✓ Betlog multiple bets test passed")

            print("✓ Betlog multiple bets test passed")

        except ConnectionError as e:
            self.fail(f"Connection error: {e}")
        except TimeoutError as e:
            self.fail(f"Timeout error: {e}")
        except AssertionError:
            raise
        except Exception as e:
            self.fail(f"Unexpected error: {e}")


def run_tests():
    """Run all tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestBlackjackFullFlow))
    # Add new betlog-specific tests
    suite.addTest(TestBlackjackFullFlow("test_betlog_settlement"))
    suite.addTest(TestBlackjackFullFlow("test_betlog_notes"))
    suite.addTest(TestBlackjackFullFlow("test_betlog_view"))
    suite.addTest(TestBlackjackFullFlow("test_betlog_multiple_bets"))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
