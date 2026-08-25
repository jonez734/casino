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
from bbsengine6.net.ping import PingUnavailable, connect as _net_connect

from .menu import menu as _client_menu
from .table_render import _safe_int_str, _signed_str, render_table

if TYPE_CHECKING:
    from bbsengine6 import WebSocketClientProtocol


class CasinoClient:
    """Terminal client for casino system."""

    auth_prompt: Callable | None = None
    _VALID_GAME_TYPES: frozenset[str] = frozenset(
        {"blackjack", "poker", "slots", "yahtzee", "tictactoe"}
    )

    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.ws: WebSocketClientProtocol | None = None
        self.connected = False
        self.authenticated = False
        self.moniker = ""
        self.balance = 0
        self.current_table_moniker: str | None = None
        self.watched_tables: set[str] = set()
        self.current_table_game_type: str | None = None
        self.current_table_players: int = 0
        self.last_available_actions: list[str] = []
        self._receive_task: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._bearer_token: str | None = None

    async def connect(self) -> bool:
        """Connect to the server.

        Routes the WebSocket connect through
        :func:`bbsengine6.net.ping.connect` so connection-level
        failures (``ConnectionRefusedError``, ``OSError``,
        ``asyncio.TimeoutError``, ``WebSocketException``) share
        the same :class:`bbsengine6.net.ping.PingUnavailable`
        code path as :func:`bedping`, :func:`bbsengine6-ping`,
        etc. On failure, the operator sees a one-line friendly
        message via :func:`bbsengine6.io.echo` with
        ``level="error"`` instead of a Python traceback.
        """
        host = getattr(self.args, "bed_host", "localhost")
        port = int(getattr(self.args, "bed_port", 8765))
        path = getattr(self.args, "bed_path", "/")
        uri = f"ws://{host}:{port}{path}"
        try:
            self.ws = await _net_connect(
                host, port, path=path, prog="casino",
                ping_interval=60,
                ping_timeout=600,
            )
            self.connected = True
            io.echo(f"Connected to {uri}")
            return True
        except PingUnavailable as exc:
            io.echo(str(exc), level="error")
            return False

    async def disconnect(self) -> None:
        """Disconnect from the server."""
        if self._receive_task:
            self._receive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._receive_task

        if self.ws:
            await self.ws.close()
            with contextlib.suppress(Exception):
                await self.ws.wait_closed()
        self.connected = False
        io.echo("Disconnected")

    async def send(self, message: dict) -> None:
        """Send message to server.

        When ``self._bearer_token`` is set (after a successful token-
        file connect or after the server rotates it on auth), inject
        ``"token"`` on every wire call. This is the defense-in-depth
        path the casino server uses to re-verify the token against its
        token store on every op, independent of (and preferred over)
        the WS-bound session token. When no token is set, the payload
        is sent verbatim so legacy / prompt-based sessions keep the
        old shape.
        """
        if not self.ws:
            return
        payload = dict(message)
        token = (self._bearer_token or "").strip()
        if token:
            payload["token"] = token
        await self.ws.send(json.dumps(payload))

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

        if msg_type in ("auth_result", "reconnect_result"):
            if msg.get("success"):
                self.authenticated = True
                self.moniker = msg.get("moniker", "")
                self.balance = msg.get("balance", 0)
                # Stash the bearer token so ``send`` auto-injects it
                # on every subsequent wire call. Bed's AuthService
                # mints the token at auth time (and rotates it on
                # every successful ``reconnect``); without this
                # capture the prompt-based legacy flow loses it on
                # the very next op and the per-op wire-token gate
                # rejects the call as ``not_authenticated``. The
                # legacy standalone / door-mode AuthService envelope
                # has no ``token`` field, in which case
                # ``_bearer_token`` stays None and ``send`` falls
                # back to session-only payloads.
                #
                # ``reconnect_result`` carries a rotated token (the
                # server invalidates the one we just sent), so we
                # capture it unconditionally -- the previous token
                # is no longer valid against the token store and
                # failing to overwrite it would leave every
                # subsequent op rejected as ``token_revoked``.
                token = (msg.get("token") or "").strip()
                if token:
                    self._bearer_token = token
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
                rows = [
                    [
                        t["moniker"],
                        t["game_type"],
                        _safe_int_str(t["min_bet"]),
                        _safe_int_str(t["max_bet"]),
                        ", ".join(t.get("players", [])) or "(empty)",
                    ]
                    for t in tables
                ]
                for line in render_table(
                    ["Moniker", "Game", "Min", "Max", "Players"],
                    rows,
                    alignments=["l", "l", "r", "r", "l"],
                ):
                    io.echo(line)

        elif msg_type == "table_created":
            moniker = msg.get("moniker", "")
            location = msg.get("location", "")
            hidden = bool(msg.get("hidden", False))
            message = msg.get("message", f"Table {moniker} created")
            util.heading(f"Table created: {moniker}")
            io.echo(
                f"{{var:labelcolor}}location:    {{var:valuecolor}}{location}"
            )
            io.echo(
                f"{{var:labelcolor}}visibility:  {{var:valuecolor}}"
                f"{'hidden' if hidden else 'public'}"
            )
            io.echo(
                f"{{var:labelcolor}}status:      {{var:valuecolor}}{message}"
            )
            io.echo(
                f"{{var:labelcolor}}note:        "
                f"use {{var:optioncolor}}[J]{{var:labelcolor}} Join with this moniker to sit down"
            )

        elif msg_type == "table_exists":
            label_for_key = {
                "blackjack": (
                    "hands_played", "wins", "losses", "pushes",
                    "blackjacks", "busts", "surrenders", "net",
                ),
                "slots": ("spins", "wins", "losses", "net"),
                "yahtzee": ("hands_played", "wins", "losses", "net"),
                "tictactoe": ("hands_played", "wins", "losses", "draws", "net"),
                "poker": ("hands_played",),
            }
            moniker = msg.get("moniker", "")
            game_type = msg.get("game_type", "")
            stats = msg.get("stats", {}) or {}
            util.heading(f"Table already exists: {moniker}")
            io.echo(
                f"{{var:labelcolor}}game:        {{var:valuecolor}}{game_type}"
            )
            io.echo(
                f"{{var:labelcolor}}owner:       {{var:valuecolor}}{msg.get('owner','')}"
            )
            io.echo(
                f"{{var:labelcolor}}location:    {{var:valuecolor}}{msg.get('location','')}"
            )
            io.echo(
                "{{var:labelcolor}}visibility:  "
                + f"{{var:valuecolor}}{'hidden' if msg.get('hidden') else 'public'}"
            )
            keys = label_for_key.get(game_type, ("hands_played",))
            if stats:
                io.echo(f"{{var:labelcolor}}stats:{{var:valuecolor}}")
                for key in keys:
                    if key not in stats:
                        continue
                    value = stats[key]
                    if key == "net":
                        io.echo(
                            f"{{var:labelcolor}}  {key:<14}"
                            f"{{var:valuecolor}}{int(value):+d}"
                        )
                    else:
                        io.echo(
                            f"{{var:labelcolor}}  {key:<14}"
                            f"{{var:valuecolor}}{int(value)}"
                        )
            else:
                io.echo("{var:labelcolor}(no hands played yet){var:normalcolor}")
            io.echo(
                f"{{var:labelcolor}}note:        {{var:valuecolor}}{msg.get('message','')}"
            )

        elif msg_type == "table_updated":
            moniker = msg.get("moniker", "")
            message = msg.get("message", "")
            util.heading(f"Table updated: {moniker}")
            if message:
                io.echo(f"{{var:labelcolor}}status:  {{var:valuecolor}}{message}")
            if self.current_table_moniker == moniker:
                self.current_table_moniker = None
                self.current_table_game_type = None

        elif msg_type == "joined_table":
            moniker = msg.get("moniker", "")
            message = msg.get("message", "")
            if moniker:
                self.current_table_moniker = moniker
            util.heading(f"Joined table: {moniker}")
            if message:
                io.echo(f"{{var:labelcolor}}status:  {{var:valuecolor}}{message}")
            io.echo(
                "{{var:labelcolor}}note:    "
                "{{var:valuecolor}}use [L]eave to get up, or place a bet to play"
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
                rows = [
                    [
                        t["id"],
                        t["from_table"],
                        t["to_table"],
                        _safe_int_str(t["amount"]),
                        t["requested_by"],
                    ]
                    for t in transfers
                ]
                for line in render_table(
                    ["ID", "From", "To", "Amount", "By"],
                    rows,
                    alignments=["r", "l", "l", "r", "l"],
                ):
                    io.echo(line)

        elif msg_type == "bank_history":
            transactions = msg.get("transactions", [])
            moniker = msg.get("moniker")
            io.echo(f"{{f6}}Transaction history for {moniker}:{{f6}}")
            rows = []
            for t in transactions:
                date = t.get("dateposted", "")[:19] if t.get("dateposted") else ""
                rows.append(
                    [
                        date,
                        t.get("type", ""),
                        _safe_int_str(t.get("amount", 0)),
                        t.get("description", ""),
                    ]
                )
            for line in render_table(
                ["Date", "Type", "Amount", "Description"],
                rows,
                alignments=["l", "l", "r", "l"],
            ):
                io.echo(line + "{f6}")

        elif msg_type == "bank_list_all":
            tables = msg.get("tables", [])
            io.echo("")
            rows = [
                [
                    t["moniker"],
                    t["owner"],
                    _safe_int_str(t["bank"]),
                    _safe_int_str(t["max_transfer"]),
                    t["type"],
                ]
                for t in tables
            ]
            for line in render_table(
                ["Moniker", "Owner", "Bank", "Max Transfer", "Type"],
                rows,
                alignments=["l", "l", "r", "r", "l"],
            ):
                io.echo(line)

        elif msg_type == "slot_result":
            spin = msg.get("spin") or {}
            util.heading(f"Slot spin at {msg.get('table_moniker')}")
            io.echo(
                f"{{var:labelcolor}}bet:      {{var:valuecolor}}{spin.get('bet', 0)}"
            )
            io.echo(
                f"{{var:labelcolor}}payout:   {{var:valuecolor}}{spin.get('payout', 0)}"
            )
            io.echo(
                f"{{var:labelcolor}}net:      {{var:valuecolor}}{spin.get('net', 0):+d}"
            )
            new_balance = spin.get("new_balance")
            if new_balance is not None:
                self.balance = int(new_balance)
                io.echo(
                    f"{{var:labelcolor}}balance:  {{var:valuecolor}}{new_balance}"
                )
            center = spin.get("center_row") or []
            if center:
                io.echo(
                    f"{{var:labelcolor}}center:   {{var:valuecolor}}{' '.join(str(s) for s in center)}"
                )

        elif msg_type == "slot_paytable":
            table_moniker = msg.get("moniker", "")
            payouts = msg.get("payouts", []) or []
            util.heading(f"Paytable for {table_moniker}")
            if not payouts:
                io.echo("{var:labelcolor}(no payouts defined)")
            else:
                rows = [
                    [
                        " ".join(p.get("symbols") or []),
                        _safe_int_str(p.get("multiplier", 0)),
                    ]
                    for p in payouts
                ]
                for line in render_table(
                    ["symbols", "multiplier"],
                    rows,
                    alignments=["l", "r"],
                ):
                    io.echo(line)

        elif msg_type == "slot_history":
            spins = msg.get("spins", []) or []
            util.heading("Slot history")
            if not spins:
                io.echo("{var:labelcolor}(no spins recorded)")
            else:
                rows = [
                    [
                        (s.get("spun_at") or "")[:19],
                        _safe_int_str(s.get("bet", 0)),
                        _safe_int_str(s.get("payout", 0)),
                        _signed_str(s.get("net", 0)),
                        s.get("table_moniker", ""),
                    ]
                    for s in spins
                ]
                for line in render_table(
                    ["when", "bet", "payout", "net", "table"],
                    rows,
                    alignments=["l", "r", "r", "r", "l"],
                ):
                    io.echo(line)

        elif msg_type == "slot_table_history":
            table_moniker = msg.get("table_moniker", "")
            spins = msg.get("spins", []) or []
            util.heading(f"Slot history for {table_moniker}")
            if not spins:
                io.echo("{var:labelcolor}(no spins recorded)")
            else:
                rows = [
                    [
                        (s.get("spun_at") or "")[:19],
                        _safe_int_str(s.get("bet", 0)),
                        _safe_int_str(s.get("payout", 0)),
                        _signed_str(s.get("net", 0)),
                        s.get("player_moniker", ""),
                    ]
                    for s in spins
                ]
                for line in render_table(
                    ["when", "bet", "payout", "net", "player"],
                    rows,
                    alignments=["l", "r", "r", "r", "l"],
                ):
                    io.echo(line)

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

    def cmd_slot_spin(self) -> None:
        """Handle slot_spin command.

        Prompts for the bet amount and sends a ``slot_spin`` wire
        message. ``CasinoClient.send`` auto-injects the bearer token
        when one is bound (``self._bearer_token``), so the WS handler
        re-verifies it on every op. The reply arrives as a
        ``slot_result`` message routed through ``handle_message``.
        """
        if self.current_table_moniker is None:
            io.echo("Not at a table. Use Join first.", level="error")
            return
        bet = io.inputinteger("{var:promptcolor}Bet amount: {var:inputcolor}", minimum=1)
        if bet is None:
            return
        self._loop.run_until_complete(
            self.send(
                {
                    "type": "slot_spin",
                    "bet": int(bet),
                }
            )
        )

    def cmd_slot_paytable(self) -> None:
        """Handle slot_paytable command."""
        if self.current_table_moniker is None:
            io.echo("Not at a table. Use Join first.", level="error")
            return
        self._loop.run_until_complete(self.send({"type": "slot_paytable"}))

    def cmd_slot_history(self) -> None:
        """Handle slot_history command."""
        limit = io.inputinteger(
            "{var:promptcolor}Number of recent spins (default 20): {var:inputcolor}",
            default=20,
        )
        if limit is None:
            limit = 20
        self._loop.run_until_complete(
            self.send(
                {
                    "type": "slot_history",
                    "limit": int(limit),
                }
            )
        )

    @staticmethod
    def _verify_game_type(raw: str, **kwargs) -> bool:
        """verify= callback for cmd_create_table's inputstring prompt.

        Accepts the input only if its lowercase, stripped form is one
        of :attr:`_VALID_GAME_TYPES`. ``inputstring`` re-prompts on
        False, so an invalid value cannot escape to the wire. The
        same set will be wired into a tab-completion Completer later
        without changing the prompt shape.

        ``**kwargs`` swallows internal kwargs that ``io.inputstring``
        forwards to verify callables (e.g. ``_history``,
        ``_history_enabled``, ``_insert_mode``,
        ``_function_key_callbacks``, ``f1_help``, ``pagesize``,
        ``beep_on_error``).
        """
        return raw.strip().lower() in CasinoClient._VALID_GAME_TYPES

    def cmd_create_table(self) -> None:
        """Handle create_table command.

        Uses ``io.inputstring`` (not ``inputchoice``) because the
        game type is a multi-character word, not a single key. A
        ``verify=`` callback enforces membership in
        :attr:`_VALID_GAME_TYPES` so the wire call cannot carry an
        unsupported value. A ``Completer`` will be attached here
        later for tab completion without changing the prompt shape.
        """
        game_type = io.inputstring(
            "{var:promptcolor}Game type: "
            "{var:optioncolor}[blackjack|poker|slots|yahtzee|tictactoe]"
            "{var:promptcolor}: {var:inputcolor}",
            verify=self._verify_game_type,
        ).strip().lower()
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
        moniker = io.inputstring("{var:promptcolor}Table moniker: {var:inputcolor}")
        if not moniker:
            io.echo("{errorcolor}moniker required{/all}", level="error")
            return

        self._loop.run_until_complete(
            self.send(
                {
                    "type": "join_table",
                    "moniker": moniker,
                }
            )
        )
        self.current_table_moniker = moniker

    def cmd_leave_table(self) -> None:
        """Handle leave_table command."""
        self._loop.run_until_complete(
            self.send(
                {
                    "type": "leave_table",
                    "moniker": self.current_table_moniker,
                }
            )
        )
        self.current_table_moniker = None
        self.current_table_game_type = None

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
                    "moniker": self.current_table_moniker,
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
                "{var:promptcolor}{var:optioncolor}[B]{var:labelcolor}alance{/all}{f6}{var:optioncolor}[A]{var:labelcolor}dd{/all}{f6}{var:optioncolor}[W]{var:labelcolor}ithdraw{/all}{f6}{var:optioncolor}[T]{var:labelcolor}ransfer{/all}{f6}{var:optioncolor}[P]{var:labelcolor}ending{/all}{f6}{var:optioncolor}[H]{var:labelcolor}istory{/all}{f6}{var:optioncolor}[L]{var:labelcolor}ist all{/all}{f6}{var:optioncolor}[Q]{var:labelcolor}uit{/all}{var:promptcolor}: {var:inputcolor}",
                "b,a,w,t,p,h,l,q",
                default="q",
            )

            if cmd == "b":
                io.echo("Balance")
                self.cmd_bank_balance()
            elif cmd == "a":
                io.echo("Add")
                self.cmd_bank_add()
            elif cmd == "w":
                io.echo("Withdraw")
                self.cmd_bank_remove()
            elif cmd == "t":
                io.echo("Transfer")
                self.cmd_bank_transfer()
            elif cmd == "p":
                io.echo("Pending")
                self.cmd_bank_pending()
            elif cmd == "h":
                io.echo("History")
                self.cmd_bank_history()
            elif cmd == "l":
                io.echo("List all")
                self.cmd_bank_list_all()
            elif cmd == "q":
                break

            self._loop.run_until_complete(asyncio.sleep(0.1))

    def run(self) -> None:
        """Run the client - auto-connect, direct to auth.

        When ``args.token_file`` points at a non-empty token file (set
        either by ``--token-file`` on the merged CLI or by
        :func:`bed.tools._token.ensure_token_file_arg`'s default-path
        resolution in :func:`casino.__main__.main`), bind the existing
        bearer token via :func:`casino.auth._connect_with_token`
        (which mirrors ``bed tools bank``'s ``auth reconnect`` flow).
        Otherwise fall back to the legacy prompt-based flow:
        ``self.connect()`` then ``self.cmd_auth()``.
        """
        from .. import auth

        token_path = getattr(self.args, "token_file", None)
        if token_path:
            host = getattr(self.args, "bed_host", "127.0.0.1")
            port = int(getattr(self.args, "bed_port", 8765))
            if not auth._connect_with_token(self.args, host, port, client=self):
                return
        else:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            if not self._loop.run_until_complete(self.connect()):
                auth._close_loop_for(self)
                return

            self._receive_task = self._loop.create_task(self.receive_loop())

            self._loop.run_until_complete(self.cmd_auth())
            self._loop.run_until_complete(asyncio.sleep(0.5))

        while self.connected and self.authenticated:
            cmd = _client_menu(self)

            if cmd == "T":
                io.echo("Tables")
                self.cmd_list_tables()
            elif cmd == "C":
                io.echo("Create Table")
                self.cmd_create_table()
            elif cmd == "U":
                io.echo("Update")
                self.cmd_update_table()
            elif cmd == "J":
                io.echo("Join")
                self.cmd_join_table()
            elif cmd == "L":
                io.echo("Leave")
                self.cmd_leave_table()
            elif cmd == "B":
                io.echo("Bet")
                self.cmd_bet()
            elif cmd == "H":
                io.echo("Hit")
                self._loop.run_until_complete(self.send({"type": "hit"}))
            elif cmd == "S":
                io.echo("Stand")
                self._loop.run_until_complete(self.send({"type": "stand"}))
            elif cmd == "M":
                io.echo("Message")
                if self.current_table_moniker:
                    self.cmd_table_chat()
                else:
                    self.cmd_chat()
            elif cmd == "K":
                io.echo("Bank")
                self.cmd_bank_menu()
            elif cmd == "X":
                io.echo("Tic Tac Toe")
                self.cmd_tictactoe_quick_play()
            elif cmd == "V":
                io.echo("Move")
                self.cmd_tictactoe_move()
            elif cmd == "N":
                io.echo("Join TicTacToe Table")
                self.cmd_tictactoe_join()
            elif cmd == "G":
                io.echo("Resign")
                self.cmd_tictactoe_resign()
            elif cmd == "Q":
                break

            self._loop.run_until_complete(asyncio.sleep(0.1))

        self._loop.run_until_complete(self.disconnect())
        auth._close_loop_for(self)
