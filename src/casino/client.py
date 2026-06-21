#!/usr/bin/env python3
# casino/client.py
# Terminal UI client for casino system

import argparse
import asyncio
import json
import logging
import sys

# Add src to path for imports
sys.path.insert(0, "/home/opencode/data/work/casino/src")

import websockets

# Use bbsengine6 io for terminal I/O (synchronous)
from bbsengine6 import io

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class CasinoClient:
    """Terminal client for casino system."""

    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.ws: websockets.WebSocketClientProtocol | None = None
        self.connected = False
        self.authenticated = False
        self.moniker = ""
        self.balance = 0
        self.current_table: int | None = None
        self._receive_task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    async def connect(self) -> bool:
        """Connect to the server."""
        uri = f"ws://{self.args.host}:{self.args.port}/"
        try:
            self.ws = await websockets.connect(uri)
            self.connected = True
            io.echo(f"Connected to {uri}\n")
            return True
        except Exception as e:
            io.echo(f"Failed to connect: {e}\n")
            return False

    async def disconnect(self) -> None:
        """Disconnect from the server."""
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        if self.ws:
            await self.ws.close()
        self.connected = False
        io.echo("Disconnected\n")

    async def send(self, message: dict) -> None:
        """Send message to server."""
        if not self.ws:
            return
        await self.ws.send(json.dumps(message))

    async def receive(self) -> dict | None:
        """Receive message from server."""
        if not self.ws:
            return None
        try:
            data = await self.ws.recv()
            return json.loads(data)
        except websockets.exceptions.ConnectionClosed:
            return None
        except json.JSONDecodeError:
            return None

    async def receive_loop(self) -> None:
        """Background task to receive messages."""
        while self.connected:
            msg = await self.receive()
            if msg:
                await self.handle_message(msg)
            else:
                break

    async def handle_message(self, msg: dict) -> None:
        """Handle incoming message."""
        msg_type = msg.get("type")

        if msg_type == "auth_result":
            if msg.get("success"):
                self.authenticated = True
                self.moniker = msg.get("moniker", "")
                self.balance = msg.get("balance", 0)
                io.echo(f"Authenticated as {self.moniker}, balance: {self.balance}\n")
            else:
                io.echo(f"Authentication failed: {msg.get('message')}\n")

        elif msg_type == "table_list":
            tables = msg.get("tables", [])
            if not tables:
                io.echo("No tables available.\n")
            else:
                io.echo(f"{'ID':<4} {'Game':<12} {'Min':<6} {'Max':<6} {'Players':<20}\n")
                io.echo("-" * 52 + "\n")
                for t in tables:
                    players = ", ".join(t.get("players", [])) or "(empty)"
                    io.echo(
                        f"{t['id']:<4} {t['game_type']:<12} "
                        f"{t['min_bet']:<6} {t['max_bet']:<6} {players:<20}\n"
                    )

        elif msg_type == "game_state":
            await self.display_game_state(msg)

        elif msg_type == "chat_message":
            from_moniker = msg.get("from_moniker", "unknown")
            message = msg.get("message", "")
            scope = msg.get("scope", "global")
            prefix = f"[{scope}]" if scope == "table" else "[global]"
            io.echo(f"{prefix} {from_moniker}: {message}\n")

        elif msg_type == "error":
            io.echo(f"Error: {msg.get('message')}\n")

        elif msg_type == "pong":
            io.echo("Pong\n")

        else:
            # Debug: show unknown messages
            logger.debug(f"Unknown message type: {msg_type}: {msg}")

    async def display_game_state(self, state: dict) -> None:
        """Display game state to user."""
        io.echo("\n" + "=" * 40 + "\n")
        io.echo(f"Table {state.get('table_id')}\n")
        io.echo("-" * 40 + "\n")

        # Player's hand
        player_hand = state.get("player_hand", [])
        player_total = state.get("player_total", 0)
        if player_hand:
            cards_str = " ".join(player_hand)
            io.echo(f"Your hand: {cards_str} [{player_total}]\n")
        else:
            io.echo("No hand yet. Place a bet.\n")

        # Dealer's hand
        dealer_hand = state.get("dealer_hand", [])
        dealer_total = state.get("dealer_total", 0)
        if dealer_hand:
            cards_str = " ".join(dealer_hand)
            io.echo(f"Dealer:    {cards_str} [{dealer_total}]\n")

        io.echo("=" * 40 + "\n")

    def cmd_auth(self) -> None:
        """Handle auth command."""
        moniker = io.inputstring("Moniker: ", None, None)
        password = io.inputstring("Password: ", None, None, echo=False)

        self._loop.run_until_complete(self.send({
            "type": "auth",
            "moniker": moniker,
            "password": password,
        }))

    def cmd_list_tables(self) -> None:
        """Handle list_tables command."""
        self._loop.run_until_complete(self.send({"type": "list_tables"}))

    def cmd_create_table(self) -> None:
        """Handle create_table command."""
        game_type = io.inputchoice(
            "Game type: ",
            "blackjack,poker,slots,yahtzee",
            default="blackjack",
        )
        min_bet = io.inputinteger("Min bet: ", default=10)
        max_bet = io.inputinteger("Max bet: ", default=1000)

        self._loop.run_until_complete(self.send({
            "type": "create_table",
            "game_type": game_type,
            "min_bet": min_bet,
            "max_bet": max_bet,
        }))

    def cmd_join_table(self) -> None:
        """Handle join_table command."""
        table_id = io.inputinteger("Table ID: ")

        self._loop.run_until_complete(self.send({
            "type": "join_table",
            "table_id": table_id,
        }))
        self.current_table = table_id

    def cmd_leave_table(self) -> None:
        """Handle leave_table command."""
        self._loop.run_until_complete(self.send({
            "type": "leave_table",
            "table_id": self.current_table,
        }))
        self.current_table = None

    def cmd_bet(self) -> None:
        """Handle bet command."""
        amount = io.inputinteger("Bet amount: ")

        self._loop.run_until_complete(self.send({
            "type": "bet",
            "amount": amount,
        }))

    def cmd_chat(self) -> None:
        """Handle chat command."""
        message = io.inputstring("Message: ", None, None)

        self._loop.run_until_complete(self.send({
            "type": "chat_global",
            "message": message,
        }))

    def cmd_table_chat(self) -> None:
        """Handle table chat command."""
        message = io.inputstring("Message: ", None, None)

        self._loop.run_until_complete(self.send({
            "type": "chat_table",
            "table_id": self.current_table,
            "message": message,
        }))

    def run(self) -> None:
        """Run the main client loop (synchronous)."""
        # Run the async connect
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        if not self._loop.run_until_complete(self.connect()):
            self._loop.close()
            return

        # Start receive loop
        self._receive_task = self._loop.create_task(self.receive_loop())

        # Main command loop (synchronous)
        while self.connected:
            if not self.authenticated:
                cmd = io.inputchoice("\n[C]onnect  [Q]uit\n> ", "c,q", default="q")

                if cmd == "C":
                    self.cmd_auth()
                    self._loop.run_until_complete(asyncio.sleep(0.5))
                elif cmd == "Q":
                    break
            else:
                cmd = io.inputchoice(
                    f"\n[{self.moniker}] Balance: {self.balance}"
                    + (f" Table: {self.current_table}" if self.current_table else "")
                    + "\n[T]ables  [C]reate  [J]oin  [L]eave  [B]et  [H]it  [S]tand  [M]sg  [Q]uit\n> ",
                    "t,c,j,l,b,h,s,m,q",
                    default="q"
                )

                if cmd == "T":
                    self.cmd_list_tables()
                elif cmd == "C":
                    self.cmd_create_table()
                elif cmd == "J":
                    self.cmd_join_table()
                elif cmd == "L":
                    self.cmd_leave_table()
                elif cmd == "B":
                    self.cmd_bet()
                elif cmd == "H":
                    self._loop.run_until_complete(self.send({"type": "hit"}))
                elif cmd == "S":
                    self._loop.run_until_complete(self.send({"type": "stand"}))
                elif cmd == "M":
                    if self.current_table:
                        self.cmd_table_chat()
                    else:
                        self.cmd_chat()
                elif cmd == "Q":
                    break

                self._loop.run_until_complete(asyncio.sleep(0.1))

        self._loop.run_until_complete(self.disconnect())
        self._loop.close()


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Casino Terminal Client")
    parser.add_argument(
        "--host",
        default="localhost",
        help="Server host (default: localhost)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Server port (default: 8765)",
    )
    return parser.parse_args()


def main() -> None:
    """Main entry point."""
    args = parse_args()
    client = CasinoClient(args)

    try:
        client.run()
    except KeyboardInterrupt:
        io.echo("\nInterrupted\n")


if __name__ == "__main__":
    main()
