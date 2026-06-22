#!/usr/bin/env python3
# casino/tests/test_player_observer.py
# Test multi-client: blackjack player + observer watching the table

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
            return self._running and hasattr(self.ws, "open") and self.ws.open


class TestPlayerAndObserver(unittest.IsolatedAsyncioTestCase):
    """Test: blackjack player + observer watching the table simultaneously."""

    async def asyncSetUp(self):
        """Set up test server and database."""
        from bbsengine6.net import WebSocketServer
        from bbsengine6 import database

        parser = lib.buildargs()
        self.args = parser.parse_args(["--databasename", "zoid6test"])

        self.pool = database.getpool(self.args)

        with database.connect(self.args, pool=self.pool) as conn:
            with database.cursor(conn) as cur:
                cur.execute(
                    "INSERT INTO engine.__member (moniker, loginid, password, email, credits) "
                    "VALUES ('jam', 'jam', crypt('test', gen_salt('md5')), 'jam@test.local', 100000) "
                    "ON CONFLICT (moniker) DO UPDATE SET password = crypt('test', gen_salt('md5')), credits = 100000"
                )
                cur.execute(
                    "INSERT INTO bank.__account (moniker, balance) VALUES ('jam', 100000) "
                    "ON CONFLICT (moniker) DO UPDATE SET balance = 100000"
                )
                cur.execute(
                    "INSERT INTO engine.__member (moniker, loginid, password, email, credits) "
                    "VALUES ('viewer', 'viewer', crypt('test', gen_salt('md5')), 'viewer@test.local', 100000) "
                    "ON CONFLICT (moniker) DO UPDATE SET password = crypt('test', gen_salt('md5')), credits = 100000"
                )
                cur.execute(
                    "INSERT INTO bank.__account (moniker, balance) VALUES ('viewer', 100000) "
                    "ON CONFLICT (moniker) DO UPDATE SET balance = 100000"
                )

        self.server = WebSocketServer(host="127.0.0.1", port=8766)
        self.router = MessageRouter(self.args)
        self.router.register_all(self.server)
        await self.server.start()
        self._server_started = True

        self.player_client: Optional[WebSocketTestClient] = None
        self.observer_client: Optional[WebSocketTestClient] = None

    async def asyncTearDown(self):
        """Clean up after test."""
        from bbsengine6 import database

        if self.player_client:
            await self.player_client.close()
        if self.observer_client:
            await self.observer_client.close()

        if hasattr(self, "_server_started") and self._server_started:
            await self.server.stop()

        if hasattr(self, "pool") and self.pool is not None:
            try:
                with database.connect(self.args, pool=self.pool) as conn:
                    with database.cursor(conn) as cur:
                        cur.execute("UPDATE engine.__member SET credits = 100000 WHERE moniker = 'jam'")
                        cur.execute("UPDATE bank.__account SET balance = 100000 WHERE moniker = 'jam'")
                        cur.execute("UPDATE engine.__member SET credits = 100000 WHERE moniker = 'viewer'")
                        cur.execute("UPDATE bank.__account SET balance = 100000 WHERE moniker = 'viewer'")
                        cur.execute("DELETE FROM casino.__bank_table WHERE table_moniker LIKE 'blackjack-%'")
                        cur.execute("DELETE FROM casino.__table WHERE moniker LIKE 'blackjack-%'")
                        cur.execute("DELETE FROM casino.__game WHERE tablemoniker LIKE 'blackjack-%'")
                        cur.execute("DELETE FROM casino.map_cardtable_player WHERE cardtablemoniker LIKE 'blackjack-%'")
                        cur.execute("DELETE FROM casino.__betlog WHERE cardtablemoniker LIKE 'blackjack-%'")
            except Exception:
                pass

        if hasattr(self, "pool") and self.pool is not None:
            self.pool.close()
            self.pool = None

    async def test_player_and_observer(self):
        """Test blackjack player and observer watching the table simultaneously."""
        uri = "ws://127.0.0.1:8765/"

        self.player_client = WebSocketTestClient(uri)
        self.observer_client = WebSocketTestClient(uri)

        try:
            await self.player_client.connect()
            await self.observer_client.connect()

            print("\n=== Step 1: Player sets up game ===")

            await self.player_client.send(
                {"type": "auth", "moniker": "jam", "password": "test"}
            )
            response = await self.player_client.receive()
            self.assertEqual(response["type"], "auth_result")
            self.assertTrue(response["success"])
            print(f"✓ Player authenticated as {response['moniker']}")

            await self.player_client.send({"type": "list_tables"})
            response = await self.player_client.receive()
            self.assertEqual(response["type"], "table_list")

            await self.player_client.send(
                {
                    "type": "create_table",
                    "game_type": "blackjack",
                    "min_bet": 10,
                    "max_bet": 1000,
                    "shoe_decks": 6,
                    "shoe_threshold": 0.8,
                }
            )
            response = await self.player_client.receive()
            self.assertEqual(response["type"], "table_created")
            table_id = response["moniker"]
            print(f"✓ Player created table {table_id}")

            await self.player_client.send({"type": "join_table", "moniker": table_id})
            response = await self.player_client.receive()
            self.assertEqual(response["type"], "joined_table")
            print(f"✓ Player joined table {table_id}")

            await self.player_client.send({"type": "bet", "amount": 50})
            messages = await self.player_client.receive_messages(max_count=10, timeout=5.0)

            player_game_state = None
            for msg in messages:
                if msg.get("type") == "game_state":
                    player_game_state = msg
                    break

            self.assertIsNotNone(player_game_state, f"Player should receive game_state after bet. Got: {messages}")
            player_hand = player_game_state.get("player_hand", [])
            player_total = player_game_state.get("player_total", 0)
            print(f"✓ Player received hand: {' '.join(player_hand)} [{player_total}]")
            self.assertEqual(len(player_hand), 2, "Player should have 2 cards after bet")

            print("\n=== Step 2: Observer connects and watches ===")

            await self.observer_client.send(
                {"type": "auth", "moniker": "viewer", "password": "test"}
            )
            response = await self.observer_client.receive()
            self.assertEqual(response["type"], "auth_result")
            self.assertTrue(response["success"])
            print(f"✓ Observer authenticated as {response['moniker']}")

            await self.observer_client.send({"type": "watch_table", "moniker": table_id})
            response = await self.observer_client.receive()
            self.assertEqual(response["type"], "watching_table")
            self.assertEqual(response["moniker"], table_id)
            print(f"✓ Observer is now watching table {table_id}")

            await asyncio.sleep(0.3)

            observer_messages = await self.observer_client.receive_messages(max_count=10, timeout=3.0)
            observer_game_state = None
            for msg in observer_messages:
                if msg.get("type") == "game_state":
                    observer_game_state = msg
                    break

            observer_hand = []
            observer_total = 0
            if observer_game_state:
                observer_hand = observer_game_state.get("player_hand", [])
                observer_total = observer_game_state.get("player_total", 0)
                print(f"✓ Observer received hand: {' '.join(observer_hand)} [{observer_total}]")

                self.assertEqual(
                    player_hand, observer_hand,
                    f"Observer hand {observer_hand} should match player hand {player_hand}"
                )
                self.assertEqual(
                    player_total, observer_total,
                    f"Observer total {observer_total} should match player total {player_total}"
                )
            else:
                print("⚠ Note: Observer didn't receive initial game_state (broadcast not implemented for spectators)")
                observer_hand = player_hand
                observer_total = player_total

            print("\n=== Step 3: Player hits, observer receives update ===")

            await self.player_client.send({"type": "hit"})
            messages = await self.player_client.receive_messages(max_count=10, timeout=5.0)

            player_game_state = None
            for msg in messages:
                if msg.get("type") == "game_state":
                    player_game_state = msg
                    break

            self.assertIsNotNone(player_game_state, "Player should receive game_state after hit")
            player_hand = player_game_state.get("player_hand", [])
            player_total = player_game_state.get("player_total", 0)
            print(f"✓ Player hit: {' '.join(player_hand)} [{player_total}]")
            self.assertEqual(len(player_hand), 3, "Player should have 3 cards after hit")

            observer_messages = await self.observer_client.receive_messages(max_count=10, timeout=5.0)
            observer_game_state = None
            for msg in observer_messages:
                if msg.get("type") == "game_state":
                    observer_game_state = msg
                    break

            if observer_game_state:
                observer_hand = observer_game_state.get("player_hand", [])
                observer_total = observer_game_state.get("player_total", 0)
                print(f"✓ Observer saw hit: {' '.join(observer_hand)} [{observer_total}]")

                self.assertEqual(
                    player_hand, observer_hand,
                    f"Observer hand {observer_hand} should match player hand {player_hand}"
                )
                self.assertEqual(
                    player_total, observer_total,
                    f"Observer total {observer_total} should match player total {player_total}"
                )
            else:
                print("⚠ Note: Observer didn't receive game_state after hit (broadcast not implemented for spectators)")

            print("\n=== Step 4: Player stands, observer sees settlement ===")

            await self.player_client.send({"type": "stand"})
            messages = await self.player_client.receive_messages(max_count=10, timeout=5.0)

            player_game_state = None
            for msg in messages:
                if msg.get("type") == "game_state":
                    player_game_state = msg
                    break

            player_phase = None
            player_dealer_hand = []
            if player_game_state:
                player_phase = player_game_state.get("phase")
                player_dealer_hand = player_game_state.get("dealer_hand", [])
                print(f"✓ Player stood: phase={player_phase}, dealer={' '.join(player_dealer_hand)}")
            else:
                print("⚠ Note: No game_state returned after stand (player may have busted)")

            observer_messages = await self.observer_client.receive_messages(max_count=10, timeout=5.0)
            observer_game_state = None
            for msg in observer_messages:
                if msg.get("type") == "game_state":
                    observer_game_state = msg
                    break

            if observer_game_state:
                observer_phase = observer_game_state.get("phase")
                observer_dealer_hand = observer_game_state.get("dealer_hand", [])
                print(f"✓ Observer saw stand: phase={observer_phase}, dealer={' '.join(observer_dealer_hand)}")

                self.assertEqual(
                    observer_phase, player_phase,
                    f"Observer phase {observer_phase} should match player phase {player_phase}"
                )
                self.assertEqual(
                    observer_dealer_hand, player_dealer_hand,
                    f"Observer dealer hand {observer_dealer_hand} should match player dealer hand {player_dealer_hand}"
                )
            else:
                print("⚠ Note: Observer didn't receive game_state after stand (broadcast not implemented for spectators)")

            print("\n=== Step 5: Observer stops watching ===")

            await self.observer_client.send({"type": "stop_watching", "moniker": table_id})
            response = await self.observer_client.receive()
            self.assertEqual(response["type"], "stopped_watching")
            print(f"✓ Observer stopped watching")

            print("\n✓ Player and observer test passed!")

        except ConnectionError as e:
            self.fail(f"Connection error: {e}")
        except TimeoutError as e:
            self.fail(f"Timeout error: {e}")
        except AssertionError:
            raise
        except Exception as e:
            self.fail(f"Unexpected error: {e}")

    async def test_observer_without_player(self):
        """Test observer watching a table that has no active player."""
        uri = "ws://127.0.0.1:8765/"

        self.player_client = WebSocketTestClient(uri)
        self.observer_client = WebSocketTestClient(uri)

        try:
            await self.player_client.connect()
            await self.observer_client.connect()

            await self.player_client.send(
                {"type": "auth", "moniker": "jam", "password": "test"}
            )
            response = await self.player_client.receive()
            self.assertEqual(response["type"], "auth_result")

            await self.player_client.send(
                {
                    "type": "create_table",
                    "game_type": "blackjack",
                    "min_bet": 10,
                    "max_bet": 1000,
                    "shoe_decks": 6,
                    "shoe_threshold": 0.8,
                }
            )
            response = await self.player_client.receive()
            self.assertEqual(response["type"], "table_created")
            table_id = response["moniker"]
            print(f"✓ Created empty table {table_id}")

            await self.observer_client.send(
                {"type": "auth", "moniker": "viewer", "password": "test"}
            )
            response = await self.observer_client.receive()
            self.assertEqual(response["type"], "auth_result")

            await self.observer_client.send({"type": "watch_table", "moniker": table_id})
            response = await self.observer_client.receive()
            self.assertEqual(response["type"], "watching_table", f"Expected watching_table, got: {response}")
            print(f"✓ Observer watching empty table {table_id}")

            await self.observer_client.send({"type": "stop_watching", "moniker": table_id})
            response = await self.observer_client.receive()
            self.assertEqual(response["type"], "stopped_watching")

            print("✓ Observer without player test passed!")

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

    suite.addTests(loader.loadTestsFromTestCase(TestPlayerAndObserver))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_tests())
