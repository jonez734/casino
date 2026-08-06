# casino/client/casino_client.py
# CasinoClient: WebSocket-based terminal client for the BED casino server.

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
from typing import TYPE_CHECKING, Callable

import websockets
from bbsengine6 import io, util

if TYPE_CHECKING:
    from bbsengine6 import WebSocketClientProtocol


class CasinoClient:
    """Terminal client for casino system."""

    auth_prompt: Callable | None = None

    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.ws: WebSocketClientProtocol | None = None
        self.connected = False
        self.authenticated = False
        self.moniker = ""
        self.balance = 0
        self.current_table: int | None = None
        self.watched_tables: set[str] = set()
        self.current_table_moniker: str | None = None
        self.current_table_game_type: str | None = None
        self.current_table_players: int = 0
        self.last_available_actions: list[str] = []
        self._receive_task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    async def connect(self) -> bool:
        """Connect to the server."""
        uri = f"ws://{self.args.host}:{self.args.port}/"
        try:
            self.ws = await websockets.connect(uri)
            self.connected = True
            io.echo(f"Connected to {uri}")
            return True
        except Exception as e:
            io.echo_traceback(f"Failed to connect: {e}")
            return False

    async def disconnect(self) -> None:
        """Disconnect from the server."""
        if self._receive_task:
            self._receive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._receive_task

        if self.ws:
            await self.ws.close()
        self.connected = False
        io.echo("Disconnected")

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
                io.echo(f"Authenticated as {self.moniker}, balance: {self.balance}")
            else:
                reason = (msg.get("message") or "").lower()
                if "invalid password" in reason or "wrong password" in reason or "password" in reason:
                    io.echo(
                        "{errorcolor}Authentication failed: the password you entered is incorrect. "
                        "Reconnect and try again.{/all}"
                    )
                elif "not found" in reason:
                    io.echo(
                        "{errorcolor}Authentication failed: that moniker was not found. "
                        "Check the spelling and try again.{/all}"
                    )
                else:
                    io.echo(f"{{errorcolor}}Authentication failed: {msg.get('message')}{{/all}}")

        elif msg_type == "table_list":
            tables = msg.get("tables", [])
            if not tables:
                io.echo("No tables available.")
            else:
                io.echo(
                    f"{'ID':<4} {'Game':<12} {'Min':<6} {'Max':<6} {'Players':<20}\n"
                )
                util.hr(end="")
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
            io.echo(f"{prefix} {from_moniker}: {message}")

        elif msg_type == "error":
            io.echo(f"Error: {msg.get('message')}")

        elif msg_type == "pong":
            io.echo("Pong")

        elif msg_type == "bank_balance":
            io.echo(
                f"Table {msg.get('moniker')} bank: {msg.get('balance')}, max transfer: {msg.get('max_transfer')}\n"
            )

        elif msg_type == "bank_added":
            io.echo(
                f"Added {msg.get('amount')} to {msg.get('moniker')}. New balance: {msg.get('new_balance')}\n"
            )

        elif msg_type == "bank_removed":
            io.echo(
                f"Removed {msg.get('amount')} from {msg.get('moniker')}. New balance: {msg.get('new_balance')}\n"
            )

        elif msg_type == "bank_transfer_requested":
            io.echo(f"Transfer requested: {msg.get('message')}")

        elif msg_type == "bank_transfer_approved":
            io.echo(f"Transfer approved: {msg.get('message')}")

        elif msg_type == "bank_transfer_rejected":
            io.echo(f"Transfer rejected: {msg.get('message')}")

        elif msg_type == "bank_pending":
            transfers = msg.get("transfers", [])
            if not transfers:
                io.echo("No pending transfers.")
            else:
                io.echo(
                    f"{'ID':<4} {'From':<20} {'To':<20} {'Amount':<10} {'By':<15}\n"
                )
                util.hr(end="")
                for t in transfers:
                    io.echo(
                        f"{t['id']:<4} {t['from_table']:<20} {t['to_table']:<20} {t['amount']:<10} {t['requested_by']:<15}\n"
                    )

        elif msg_type == "bank_history":
            transactions = msg.get("transactions", [])
            moniker = msg.get("moniker")
            io.echo(f"{{f6}}Transaction history for {moniker}:{{f6}}")
            io.echo(f"{'Date':<24} {'Type':<12} {'Amount':<10} {'Description'}{{f6}}")
            util.hr()
            for t in transactions:
                date = t.get("dateposted", "")[:19] if t.get("dateposted") else ""
                amount = t.get("amount", 0)
                ttype = t.get("type", "")
                desc = t.get("description", "")
                io.echo(f"{date:<24} {ttype:<12} {amount:<10} {desc}{{f6}}")

        elif msg_type == "bank_list_all":
            tables = msg.get("tables", [])
            io.echo(
                f"\n{'Moniker':<20} {'Owner':<15} {'Bank':<10} {'Max Transfer':<12} {'Type':<10}\n"
            )
            util.hr()
            for t in tables:
                io.echo(
                    f"{t['moniker']:<20} {t['owner']:<15} {t['bank']:<10} {t['max_transfer']:<12} {t['type']:<10}\n"
                )

        else:
            io.echo(f"Unknown message type: {msg_type}: {msg}", level="debug")

    async def display_game_state(self, state: dict) -> None:
        """Display game state to user."""
        self.current_table_moniker = state.get("table_moniker")
        self.current_table_game_type = state.get("game_type", "blackjack")
        self.current_table_players = state.get("player_count", 0)

        util.heading(f"Table {state.get('table_moniker')} ({self.current_table_game_type})")

        player_hand = state.get("player_hand", [])
        player_total = state.get("player_total", 0)
        if player_hand:
            cards_str = " ".join(player_hand)
            io.echo(f"Your hand: {cards_str} [{player_total}]{{f6}}")
        else:
            io.echo("No hand yet. Place a bet.{{f6}}")

        dealer_hand = state.get("dealer_hand", [])
        dealer_total = state.get("dealer_total", 0)
        if dealer_hand:
            cards_str = " ".join(dealer_hand)
            io.echo(f"Dealer:    {cards_str} [{dealer_total}]{{f6}}")

        available_actions = state.get("available_actions", [])
        self.last_available_actions = available_actions
        if available_actions:
            io.echo(f"Actions: {', '.join(available_actions)}.{{f6}}")

    async def cmd_auth(self) -> bool:
        """Handle auth command.

        Resolves the auth prompt at call time:
            1. self.auth_prompt (class or instance attribute), or
            2. casino.auth.auth_prompt (the module-level default).

        Returns:
            True if the prompt completed, False if the user aborted.
        """
        from .. import auth
        prompt = self.auth_prompt or auth.auth_prompt
        return await prompt(self.args, self)

    def cmd_list_tables(self) -> None:
        """Handle list_tables command."""
        self._loop.run_until_complete(self.send({"type": "list_tables"}))

    def cmd_create_table(self) -> None:
        """Handle create_table command."""
        game_type = io.inputchoice(
            "{var:promptcolor}Game type: {var:optioncolor}[blackjack,poker,slots,yahtzee,tictactoe]{var:promptcolor}: {var:inputcolor}",
            "blackjack,poker,slots,yahtzee,tictactoe",
            default="blackjack",
        )
        min_bet = io.inputinteger("{var:promptcolor}Min bet: {var:inputcolor}", default=10)
        max_bet = io.inputinteger("{var:promptcolor}Max bet: {var:inputcolor}", default=1000)

        self._loop.run_until_complete(
            self.send(
                {
                    "type": "create_table",
                    "game_type": game_type,
                    "min_bet": min_bet,
                    "max_bet": max_bet,
                }
            )
        )

    def cmd_update_table(self) -> None:
        """Handle update_table command - owner or sysop only."""
        moniker = io.inputstring("{var:promptcolor}Table moniker to update: {var:inputcolor}")

        io.echo("Leave fields blank to keep current values.")
        new_moniker = io.inputstring(f"{{var:promptcolor}}New moniker [{moniker}]: {{var:inputcolor}}")
        min_bet = io.inputinteger("{var:promptcolor}Minimum bet: {var:inputcolor}")
        max_bet = io.inputinteger("{var:promptcolor}Maximum bet: {var:inputcolor}")
        status = io.inputstring("{var:promptcolor}Status (open/closed): {var:inputcolor}")

        message = {"type": "update_table", "moniker": moniker}

        if new_moniker:
            message["new_moniker"] = new_moniker
        if min_bet is not None:
            message["min_bet"] = min_bet
        if max_bet is not None:
            message["max_bet"] = max_bet
        if status in ("open", "closed"):
            message["status"] = status

        self._loop.run_until_complete(self.send(message))

    def cmd_join_table(self) -> None:
        """Handle join_table command."""
        table_id = io.inputinteger("{var:promptcolor}Table ID: {var:inputcolor}")

        self._loop.run_until_complete(
            self.send(
                {
                    "type": "join_table",
                    "table_id": table_id,
                }
            )
        )
        self.current_table = table_id

    def cmd_leave_table(self) -> None:
        """Handle leave_table command."""
        self._loop.run_until_complete(
            self.send(
                {
                    "type": "leave_table",
                    "table_id": self.current_table,
                }
            )
        )
        self.current_table = None

    def cmd_bet(self) -> None:
        """Handle bet command."""
        amount = io.inputinteger("{var:promptcolor}Bet amount: {var:inputcolor}")

        self._loop.run_until_complete(
            self.send(
                {
                    "type": "bet",
                    "amount": amount,
                }
            )
        )

    def cmd_tictactoe_quick_play(self) -> None:
        """Door-mode helper for tictactoe_quick_play. Prompts for mode
        and sends the BED message. Mode 0 = 2 AI (demo), 1 = human vs
        AI, 2 = 2 humans (requires a second player to send
        tictactoe_join)."""
        mode = io.inputinteger(
            "{var:promptcolor}Mode [0=2AI, 1=1P+1AI, 2=2P]: {var:inputcolor}",
            default=1,
        )
        if mode not in (0, 1, 2):
            io.echo("{errorcolor}mode must be 0, 1, or 2{/all}", level="error")
            return
        self._loop.run_until_complete(
            self.send(
                {
                    "type": "tictactoe_quick_play",
                    "mode": int(mode),
                }
            )
        )

    def cmd_tictactoe_move(self) -> None:
        """Door-mode helper for tictactoe_move. Prompts for a cell
        index 0-8."""
        cell = io.inputinteger("{var:promptcolor}Cell [0-8]: {var:inputcolor}")
        self._loop.run_until_complete(
            self.send(
                {
                    "type": "tictactoe_move",
                    "cell": int(cell),
                }
            )
        )

    def cmd_tictactoe_join(self) -> None:
        """Door-mode helper for tictactoe_join (mode 2: take the O seat)."""
        self._loop.run_until_complete(
            self.send({"type": "tictactoe_join"})
        )

    def cmd_tictactoe_resign(self) -> None:
        """Door-mode helper for tictactoe_resign."""
        self._loop.run_until_complete(
            self.send({"type": "tictactoe_resign"})
        )

    def cmd_chat(self) -> None:
        """Handle chat command."""
        message = io.inputstring("{var:promptcolor}Message: {var:inputcolor}", None, None)

        self._loop.run_until_complete(
            self.send(
                {
                    "type": "chat_global",
                    "message": message,
                }
            )
        )

    def cmd_table_chat(self) -> None:
        """Handle table chat command."""
        message = io.inputstring("{var:promptcolor}Message: {var:inputcolor}", None, None)

        self._loop.run_until_complete(
            self.send(
                {
                    "type": "chat_table",
                    "table_id": self.current_table,
                    "message": message,
                }
            )
        )

    def cmd_bank_balance(self) -> None:
        """Handle bank balance query."""
        moniker = io.inputstring("{var:promptcolor}Table moniker: {var:inputcolor}")

        self._loop.run_until_complete(
            self.send(
                {
                    "type": "bank_balance",
                    "moniker": moniker,
                }
            )
        )

    def cmd_bank_add(self) -> None:
        """Handle add funds to bank."""
        moniker = io.inputstring("{var:promptcolor}Table moniker: {var:inputcolor}")
        amount = io.inputinteger("{var:promptcolor}Amount to add: {var:inputcolor}")
        source = io.inputchoice("{var:promptcolor}Source (h)ouse or (p)layer: {var:optioncolor}[hP]{var:promptcolor}: {var:inputcolor}", "hp", default="h")
        source = "house" if source == "h" else "player"

        self._loop.run_until_complete(
            self.send(
                {
                    "type": "bank_add",
                    "moniker": moniker,
                    "amount": amount,
                    "source": source,
                }
            )
        )

    def cmd_bank_remove(self) -> None:
        """Handle remove funds from bank."""
        moniker = io.inputstring("{var:promptcolor}Table moniker: {var:inputcolor}")
        amount = io.inputinteger("{var:promptcolor}Amount to remove: {var:inputcolor}")

        self._loop.run_until_complete(
            self.send(
                {
                    "type": "bank_remove",
                    "moniker": moniker,
                    "amount": amount,
                    "reason": "adjustment",
                }
            )
        )

    def cmd_bank_transfer(self) -> None:
        """Handle transfer request between tables."""
        from_moniker = io.inputstring("{var:promptcolor}From table moniker: {var:inputcolor}")
        to_moniker = io.inputstring("{var:promptcolor}To table moniker: {var:inputcolor}")
        amount = io.inputinteger("{var:promptcolor}Amount to transfer: {var:inputcolor}")

        self._loop.run_until_complete(
            self.send(
                {
                    "type": "bank_transfer_request",
                    "from_moniker": from_moniker,
                    "to_moniker": to_moniker,
                    "amount": amount,
                }
            )
        )

    def cmd_bank_approve(self) -> None:
        """Handle approve transfer."""
        transfer_id = io.inputinteger("{var:promptcolor}Transfer ID to approve: {var:inputcolor}")

        self._loop.run_until_complete(
            self.send(
                {
                    "type": "bank_transfer_approve",
                    "transfer_id": transfer_id,
                }
            )
        )

    def cmd_bank_reject(self) -> None:
        """Handle reject transfer."""
        transfer_id = io.inputinteger("{var:promptcolor}Transfer ID to reject: {var:inputcolor}")

        self._loop.run_until_complete(
            self.send(
                {
                    "type": "bank_transfer_reject",
                    "transfer_id": transfer_id,
                }
            )
        )

    def cmd_bank_pending(self) -> None:
        """Handle list pending transfers."""
        moniker = io.inputstring("{var:promptcolor}Table moniker (leave empty for your tables): {var:inputcolor}")

        self._loop.run_until_complete(
            self.send(
                {
                    "type": "bank_pending",
                    "moniker": moniker if moniker else "",
                }
            )
        )

    def cmd_bank_history(self) -> None:
        """Handle bank history query."""
        moniker = io.inputstring("{var:promptcolor}Table moniker: {var:inputcolor}")
        limit = io.inputinteger("{var:promptcolor}Number of transactions to show: {var:inputcolor}", default=20)

        self._loop.run_until_complete(
            self.send(
                {
                    "type": "bank_history",
                    "moniker": moniker,
                    "limit": limit,
                }
            )
        )

    def cmd_bank_list_all(self) -> None:
        """Handle list all table balances (sysop only)."""
        self._loop.run_until_complete(
            self.send(
                {
                    "type": "bank_list_all",
                }
            )
        )

    def cmd_bank_menu(self) -> None:
        """Bank management submenu."""
        while True:
            cmd = io.inputchoice(
                "{var:promptcolor}[B]alance  [A]dd  [W]ithdraw  [T]ransfer  [P]ending  [H]istory  [L]ist all  [Q]uit: {var:inputcolor}",
                "b,a,w,t,p,h,l,q",
                default="q",
            )

            if cmd == "b":
                self.cmd_bank_balance()
            elif cmd == "a":
                self.cmd_bank_add()
            elif cmd == "w":
                self.cmd_bank_remove()
            elif cmd == "t":
                self.cmd_bank_transfer()
            elif cmd == "p":
                self.cmd_bank_pending()
            elif cmd == "h":
                self.cmd_bank_history()
            elif cmd == "l":
                self.cmd_bank_list_all()
            elif cmd == "q":
                break

            self._loop.run_until_complete(asyncio.sleep(0.1))

    def run(self) -> None:
        """Run the client - auto-connect, direct to auth."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        if not self._loop.run_until_complete(self.connect()):
            self._loop.close()
            return

        self._receive_task = self._loop.create_task(self.receive_loop())

        self._loop.run_until_complete(self.cmd_auth())
        self._loop.run_until_complete(asyncio.sleep(0.5))

        while self.connected and self.authenticated:
            cmd = io.inputchoice(
                f"{{var:promptcolor}}[{self.moniker}] Balance: {self.balance}"
                + (f" Table: {self.current_table}" if self.current_table else "")
                + "{{var:optioncolor}}[T]ables  [C]reate  [U]pdate  [J]oin  [L]eave  [B]et  [H]it  [S]tand  [M]sg  [K]  [X]TicTac  [V]Move  [N]JoinT  [G]Resign  [Q]uit{{var:promptcolor}}: {{var:inputcolor}}",
                "t,c,u,j,l,b,h,s,m,k,x,v,n,g,q",
                default="q",
            )

            if cmd == "T":
                self.cmd_list_tables()
            elif cmd == "C":
                self.cmd_create_table()
            elif cmd == "U":
                self.cmd_update_table()
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
            elif cmd == "K":
                self.cmd_bank_menu()
            elif cmd == "X":
                self.cmd_tictactoe_quick_play()
            elif cmd == "V":
                self.cmd_tictactoe_move()
            elif cmd == "N":
                self.cmd_tictactoe_join()
            elif cmd == "G":
                self.cmd_tictactoe_resign()
            elif cmd == "Q":
                break

            self._loop.run_until_complete(asyncio.sleep(0.1))

        self._loop.run_until_complete(self.disconnect())
        self._loop.close()
