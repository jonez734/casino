#!/usr/bin/env python3
# casino/connect.py
# Remote casino server connection via WebSocket

from __future__ import annotations

import argparse
import asyncio
import json
import sys

import websockets

from bbsengine6 import io, util, member
from bbsengine6.io.inputstring import Completer


_clients: dict[str, "CasinoClient"] = {}
_current_moniker: str | None = None


def get_client(moniker: str | None = None) -> "CasinoClient" | None:
    """Get a client by moniker, or the current moniker if None."""
    if moniker is None:
        moniker = _current_moniker
    return _clients.get(moniker)


def get_current_moniker() -> str | None:
    """Get the current active moniker."""
    return _current_moniker


def set_current_moniker(moniker: str | None) -> None:
    """Set the current active moniker."""
    global _current_moniker
    _current_moniker = moniker


def _casino_table_fragment(**kwargs) -> str:
    """Fragment showing current table info for remote client."""
    client = get_client()
    if client is None or client.current_table_moniker is None:
        return ""
    return f"{client.current_table_moniker} ({client.current_table_game_type}) players: {client.current_table_players}"


def init_remote_client_screen() -> None:
    """Initialize screen and register fragments for remote client."""
    from bbsengine6 import io as bbsio

    bbsio.screen.init()
    from bbsengine6 import screen as bbs_screen

    bbs_screen.register_bottombar_fragment(_casino_table_fragment)


def cleanup_remote_client_screen() -> None:
    """Unregister fragments on disconnect."""
    from bbsengine6 import screen

    screen.unregister_bottombar_fragment(_casino_table_fragment)


def resolve_action(input_str: str, actions: list[dict]) -> str | None:
    """Resolve user input to action, handling ambiguous matches.

    Args:
        input_str: User input (hotkey prefix or action name)
        actions: List of action dicts with 'action', 'label', 'hotkey' keys

    Returns:
        Action name if unambiguous, None if no match,
        Raises ValueError if ambiguous (multiple matches)
    """
    if not input_str:
        return None

    input_lower = input_str.lower()

    # First check exact hotkey match
    for action in actions:
        if action.get("hotkey", "").lower() == input_lower:
            return action["action"]

    # Then check prefix match on action names
    matches = [a for a in actions if a["action"].lower().startswith(input_lower)]

    if len(matches) == 0:
        return None

    if len(matches) == 1:
        return matches[0]["action"]

    # Multiple matches - raise error with action names
    options = ", ".join([a["action"] for a in matches])
    raise ValueError(f"Which actions? {options}")


class ActionInputHandler(Completer):
    """Handler for action input with tab completion support."""

    def __init__(self, actions: list[dict]):
        super().__init__()
        self.actions = actions
        self.action_map = {}
        for a in actions:
            self.action_map[a.get("hotkey", "").lower()] = a["action"]
            self.action_map[a["action"].lower()] = a["action"]

    def resolve(self, input_str: str) -> str | None:
        """Resolve input to action name."""
        return resolve_action(input_str, self.actions)

    def get_matches(self, prefix: str, **kwargs) -> list[str]:
        """Return list of possible completions for the prefix.

        Matches against both action names and hotkeys.
        """
        if not prefix:
            return [a["action"] for a in self.actions]

        prefix_lower = prefix.lower()
        matches = []

        for a in self.actions:
            if a["action"].lower().startswith(prefix_lower):
                matches.append(a["action"])
            elif a.get("hotkey", "").lower() == prefix_lower:
                matches.append(a["action"])

        return sorted(set(matches))

    def get_completer(self) -> "ActionInputHandler":
        """Return self for use as completer with inputstring."""
        return self


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
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

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
                io.echo(f"Authentication failed: {msg.get('message')}")

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

    def cmd_auth(self) -> None:
        """Handle auth command."""
        moniker = io.inputstring("{var:promptcolor}Moniker: {var:inputcolor}", None, None)

        password = ""
        if member.has_password(self.args, moniker):
            password = util.inputpassword("Password: ")

        self._loop.run_until_complete(
            self.send(
                {
                    "type": "auth",
                    "moniker": moniker,
                    "password": password,
                }
            )
        )

    def cmd_list_tables(self) -> None:
        """Handle list_tables command."""
        self._loop.run_until_complete(self.send({"type": "list_tables"}))

    def cmd_create_table(self) -> None:
        """Handle create_table command."""
        game_type = io.inputchoice(
            "{var:promptcolor}Game type: {var:optioncolor}[blackjack,poker,slots,yahtzee]{var:promptcolor}: {var:inputcolor}",
            "blackjack,poker,slots,yahtzee",
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

        self.cmd_auth()
        self._loop.run_until_complete(asyncio.sleep(0.5))

        while self.connected and self.authenticated:
            cmd = io.inputchoice(
                f"{{var:promptcolor}}[{self.moniker}] Balance: {self.balance}"
                + (f" Table: {self.current_table}" if self.current_table else "")
                + f"{{var:optioncolor}}[T]ables  [C]reate  [U]pdate  [J]oin  [L]eave  [B]et  [H]it  [S]tand  [M]sg  [K]  [Q]uit{{var:promptcolor}}: {{var:inputcolor}}",
                "t,c,u,j,l,b,h,s,m,k,q",
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
            elif cmd == "Q":
                break

            self._loop.run_until_complete(asyncio.sleep(0.1))

        self._loop.run_until_complete(self.disconnect())
        self._loop.close()


def init(args, **kwargs):
    """BBS module init."""
    return True


def access(args, op: str, **kwargs):
    """BBS module access check."""
    return True


def buildargs(args, **kwargs) -> argparse.ArgumentParser | None:
    """BBS module buildargs."""
    return None


def connect(args, **kwargs) -> "CasinoClient" | None:
    """Entry point - connect to server and authenticate."""
    global _current_moniker

    util.heading("connect to server")
    host = getattr(args, "host", "127.0.0.1")
    port = getattr(args, "port", 8765)
    io.echo(f"Connecting to {host}:{port}...")

    client = CasinoClient(args)
    client._loop = asyncio.new_event_loop()
    asyncio.set_event_loop(client._loop)

    if not client._loop.run_until_complete(client.connect()):
        client._loop.close()
        io.echo("Failed to connect", level="error")
        return None

    client._receive_task = client._loop.create_task(client.receive_loop())

    moniker = io.inputstring("{var:promptcolor}Moniker: {var:inputcolor}", None, None)
    password = ""
    if member.has_password(args, moniker):
        password = util.inputpassword("Password: ")

    client._loop.run_until_complete(
        client.send(
            {
                "type": "auth",
                "moniker": moniker,
                "password": password,
            }
        )
    )
    client._loop.run_until_complete(asyncio.sleep(0.5))

    if not client.authenticated:
        client._loop.run_until_complete(client.disconnect())
        client._loop.close()
        io.echo("Authentication failed", level="error")
        return None

    _clients[client.moniker] = client
    _current_moniker = client.moniker
    io.echo(f"Connected as {client.moniker}, balance: {client.balance}")
    return client


def disconnect(args, client: "CasinoClient" | None = None, **kwargs) -> bool:
    """Disconnect from server."""
    global _current_moniker

    client = client or get_client()
    if client is None:
        io.echo("Not connected.", level="error")
        return False

    client._loop.run_until_complete(client.disconnect())
    client._loop.close()

    if client.moniker in _clients:
        del _clients[client.moniker]
    if _current_moniker == client.moniker:
        _current_moniker = None

    io.echo("Disconnected.")
    return True


def main(args, **kwargs) -> bool:
    """BBS module entry point."""
    return connect(args, **kwargs)
