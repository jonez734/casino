#!/usr/bin/env python3
# casino/connect.py
# Remote casino server connection via WebSocket

import argparse
import asyncio
import json
import sys

import websockets

from bbsengine6 import io, util, member


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
        uri = f"ws://{self.args.casino_host}:{self.args.casino_port}/"
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

        elif msg_type == "bank_balance":
            io.echo(f"Table {msg.get('moniker')} bank: {msg.get('balance')}, max transfer: {msg.get('max_transfer')}\n")

        elif msg_type == "bank_added":
            io.echo(f"Added {msg.get('amount')} to {msg.get('moniker')}. New balance: {msg.get('new_balance')}\n")

        elif msg_type == "bank_removed":
            io.echo(f"Removed {msg.get('amount')} from {msg.get('moniker')}. New balance: {msg.get('new_balance')}\n")

        elif msg_type == "bank_transfer_requested":
            io.echo(f"Transfer requested: {msg.get('message')}\n")

        elif msg_type == "bank_transfer_approved":
            io.echo(f"Transfer approved: {msg.get('message')}\n")

        elif msg_type == "bank_transfer_rejected":
            io.echo(f"Transfer rejected: {msg.get('message')}\n")

        elif msg_type == "bank_pending":
            transfers = msg.get("transfers", [])
            if not transfers:
                io.echo("No pending transfers.\n")
            else:
                io.echo(f"{'ID':<4} {'From':<20} {'To':<20} {'Amount':<10} {'By':<15}\n")
                io.echo("-" * 75 + "\n")
                for t in transfers:
                    io.echo(f"{t['id']:<4} {t['from_table']:<20} {t['to_table']:<20} {t['amount']:<10} {t['requested_by']:<15}\n")

        elif msg_type == "bank_history":
            transactions = msg.get("transactions", [])
            moniker = msg.get("moniker")
            io.echo(f"\nTransaction history for {moniker}:\n")
            io.echo(f"{'Date':<24} {'Type':<12} {'Amount':<10} {'Description'}\n")
            io.echo("-" * 80 + "\n")
            for t in transactions:
                date = t.get("dateposted", "")[:19] if t.get("dateposted") else ""
                amount = t.get("amount", 0)
                ttype = t.get("type", "")
                desc = t.get("description", "")
                io.echo(f"{date:<24} {ttype:<12} {amount:<10} {desc}\n")

        elif msg_type == "bank_list_all":
            tables = msg.get("tables", [])
            io.echo(f"\n{'Moniker':<20} {'Owner':<15} {'Bank':<10} {'Max Transfer':<12} {'Type':<10}\n")
            io.echo("-" * 75 + "\n")
            for t in tables:
                io.echo(f"{t['moniker']:<20} {t['owner']:<15} {t['bank']:<10} {t['max_transfer']:<12} {t['type']:<10}\n")

        else:
            io.echo(f"Unknown message type: {msg_type}: {msg}", level="debug")

    async def display_game_state(self, state: dict) -> None:
        """Display game state to user."""
        io.echo("\n" + "=" * 40 + "\n")
        io.echo(f"Table {state.get('table_id')}\n")
        io.echo("-" * 40 + "\n")

        player_hand = state.get("player_hand", [])
        player_total = state.get("player_total", 0)
        if player_hand:
            cards_str = " ".join(player_hand)
            io.echo(f"Your hand: {cards_str} [{player_total}]\n")
        else:
            io.echo("No hand yet. Place a bet.\n")

        dealer_hand = state.get("dealer_hand", [])
        dealer_total = state.get("dealer_total", 0)
        if dealer_hand:
            cards_str = " ".join(dealer_hand)
            io.echo(f"Dealer:    {cards_str} [{dealer_total}]\n")

        io.echo("=" * 40 + "\n")

    def cmd_auth(self) -> None:
        """Handle auth command."""
        moniker = io.inputstring("Moniker: ", None, None)

        password = ""
        if member.has_password(self.args, moniker):
            password = util.inputpassword("Password: ")

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

    def cmd_update_table(self) -> None:
        """Handle update_table command - owner or sysop only."""
        moniker = io.inputstring("Table moniker to update: ")
        
        io.echo("Leave fields blank to keep current values.")
        new_moniker = io.inputstring(f"New moniker [{moniker}]: ")
        min_bet = io.inputinteger("Minimum bet: ")
        max_bet = io.inputinteger("Maximum bet: ")
        status = io.inputstring("Status (open/closed): ")
        
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

    def cmd_bank_balance(self) -> None:
        """Handle bank balance query."""
        moniker = io.inputstring("Table moniker: ")
        
        self._loop.run_until_complete(self.send({
            "type": "bank_balance",
            "moniker": moniker,
        }))

    def cmd_bank_add(self) -> None:
        """Handle add funds to bank."""
        moniker = io.inputstring("Table moniker: ")
        amount = io.inputinteger("Amount to add: ")
        source = io.inputchoice("Source (h)ouse or (p)layer: ", "hp", default="h")
        source = "house" if source == "h" else "player"
        
        self._loop.run_until_complete(self.send({
            "type": "bank_add",
            "moniker": moniker,
            "amount": amount,
            "source": source,
        }))

    def cmd_bank_remove(self) -> None:
        """Handle remove funds from bank."""
        moniker = io.inputstring("Table moniker: ")
        amount = io.inputinteger("Amount to remove: ")
        
        self._loop.run_until_complete(self.send({
            "type": "bank_remove",
            "moniker": moniker,
            "amount": amount,
            "reason": "adjustment",
        }))

    def cmd_bank_transfer(self) -> None:
        """Handle transfer request between tables."""
        from_moniker = io.inputstring("From table moniker: ")
        to_moniker = io.inputstring("To table moniker: ")
        amount = io.inputinteger("Amount to transfer: ")
        
        self._loop.run_until_complete(self.send({
            "type": "bank_transfer_request",
            "from_moniker": from_moniker,
            "to_moniker": to_moniker,
            "amount": amount,
        }))

    def cmd_bank_approve(self) -> None:
        """Handle approve transfer."""
        transfer_id = io.inputinteger("Transfer ID to approve: ")
        
        self._loop.run_until_complete(self.send({
            "type": "bank_transfer_approve",
            "transfer_id": transfer_id,
        }))

    def cmd_bank_reject(self) -> None:
        """Handle reject transfer."""
        transfer_id = io.inputinteger("Transfer ID to reject: ")
        
        self._loop.run_until_complete(self.send({
            "type": "bank_transfer_reject",
            "transfer_id": transfer_id,
        }))

    def cmd_bank_pending(self) -> None:
        """Handle list pending transfers."""
        moniker = io.inputstring("Table moniker (leave empty for your tables): ")
        
        self._loop.run_until_complete(self.send({
            "type": "bank_pending",
            "moniker": moniker if moniker else "",
        }))

    def cmd_bank_history(self) -> None:
        """Handle bank history query."""
        moniker = io.inputstring("Table moniker: ")
        limit = io.inputinteger("Number of transactions to show: ", default=20)
        
        self._loop.run_until_complete(self.send({
            "type": "bank_history",
            "moniker": moniker,
            "limit": limit,
        }))

    def cmd_bank_list_all(self) -> None:
        """Handle list all table balances (sysop only)."""
        self._loop.run_until_complete(self.send({
            "type": "bank_list_all",
        }))

    def cmd_bank_menu(self) -> None:
        """Bank management submenu."""
        while True:
            cmd = io.inputchoice(
                "\n[B]alance  [A]dd  [W]ithdraw  [T]ransfer  "
                "[P]ending  [H]istory  [L]ist all  [Q]uit: ",
                "b,a,w,t,p,h,l,q",
                default="q"
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
                f"\n[{self.moniker}] Balance: {self.balance}"
                + (f" Table: {self.current_table}" if self.current_table else "")
                + "\n[T]ables  [C]reate  [U]pdate  [J]oin  [L]eave  "
                + "[B]et  [H]it  [S]tand  [M]sg  [K]  [Q]uit\n> ",
                "t,c,u,j,l,b,h,s,m,k,q",
                default="q"
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


def connect(args, **kwargs) -> bool:
    """Entry point - launch remote client."""
    util.heading("connect to server")
    host = getattr(args, "casino_host", "localhost")
    port = getattr(args, "casino_port", 8765)
    io.echo(f"Connecting to {host}:{port}...\n")
    client = CasinoClient(args)
    client.run()
    return True


def main(args, **kwargs) -> bool:
    """BBS module entry point."""
    return connect(args, **kwargs)
