# casino/api/handler.py
# WebSocket message handler - routes messages to services using bbsengine6.net service registry

from datetime import datetime
from typing import Any, Dict, Optional

from bbsengine6 import io, member, database
from bbsengine6.message import deliver_pending_on_connect, get_unread_count
from bbsengine6.net import (
    ChannelState,
    channel_subscribe,
    channel_unsubscribe,
    channel_unsubscribe_all,
)
from bbsengine6.message_delivery import send as notify_send, NotificationUrgency
from casino.dal import player as dal_player
from casino.dal.aiosql import table as async_dal_table
from casino.yahtzee.api_handler import YahtzeeServiceHandler
from casino.tictactoe.api_handler import TictactoeServiceHandler


from bbsengine6.session import SessionManager


class CasinoSessionManager(SessionManager):
    """Extends base SessionManager with table/spectator tracking."""

    def __init__(self):
        super().__init__()
        self._spectators: Dict[str, set] = {}

    def register_session(self, session_id: int, moniker: str, is_sysop: bool = False) -> None:
        super().register_session(session_id, moniker, is_sysop)
        self._sessions[session_id]["table_moniker"] = None

    def unregister_session(self, session_id: int) -> None:
        if session_id in self._sessions:
            table_moniker = self._sessions[session_id].get("table_moniker")
            if table_moniker and table_moniker in self._spectators:
                self._spectators[table_moniker].discard(session_id)
        super().unregister_session(session_id)

    def get_table_moniker(self, session_id: int) -> Optional[str]:
        session = self._sessions.get(session_id)
        return session.get("table_moniker") if session else None

    def set_table_moniker(self, session_id: int, table_moniker: Optional[str]) -> None:
        io.echo(f"set_table_moniker: session_id={session_id}, table_moniker={table_moniker}", level="info")
        if session_id in self._sessions:
            self._sessions[session_id]["table_moniker"] = table_moniker
        else:
            io.echo(f"set_table_moniker: session {session_id} not found in sessions", level="warning")

    def add_spectator(self, table_moniker: str, session_id: int) -> None:
        if table_moniker not in self._spectators:
            self._spectators[table_moniker] = set()
        self._spectators[table_moniker].add(session_id)

    def remove_spectator(self, table_moniker: str, session_id: int) -> None:
        if table_moniker in self._spectators:
            self._spectators[table_moniker].discard(session_id)

    def get_table_observers(self, table_moniker: str) -> set:
        return self._spectators.get(table_moniker, set())

    def get_table_player_count(self, table_moniker: str) -> int:
        return sum(
            1
            for s in self._sessions.values()
            if s.get("table_moniker") == table_moniker
        )


class BaseService:
    """Base class for message handlers."""
    
    def __init__(self, args: Any, session_manager: SessionManager):
        self.args = args
        self.sessions = session_manager
    
    async def handle_message(
        self, server: Any, websocket: Any, path: str, message: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        raise NotImplementedError


class AuthService(BaseService):
    """Handle authentication messages."""
    
    from casino.services.player import PlayerService
    
    def __init__(self, args: Any, session_manager: SessionManager, channel_state: Optional[ChannelState] = None):
        super().__init__(args, session_manager)
        self.player_service = self.PlayerService(args)
        self.channel_state = channel_state
    
    async def handle_message(
        self, server: Any, websocket: Any, path: str, message: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        msg_type = message.get("type")
        
        if msg_type == "auth":
            return await self._handle_auth(websocket, message)
        elif msg_type == "ping":
            return {"type": "pong", "timestamp": datetime.utcnow().isoformat()}
        
        return None
    
    async def _handle_auth(self, websocket: Any, message: Dict[str, Any]) -> Dict[str, Any]:
        moniker = message.get("moniker", "")
        password = message.get("password", "")
        
        if not moniker:
            return {"type": "error", "code": "invalid_credentials", "message": "Moniker and password required"}
        
        result = self.player_service.authenticate(moniker, password)
        
        if result["success"]:
            session_id = id(websocket)
            is_sysop = member.issysop(self.args, moniker=moniker) is True
            self.sessions.register_session(session_id, moniker, is_sysop=is_sysop)
            balance = self.player_service.get_balance(moniker)
            
            # Auto-subscribe to personal channel for direct messages
            if self.channel_state:
                channel_subscribe(self.channel_state, session_id, f"member:{moniker}")
            
            # Deliver pending messages on connect
            pending_messages = []
            try:
                pending_messages = deliver_pending_on_connect(moniker, database=self.args.databasename)
            except Exception as e:
                io.echo(f"Failed to deliver pending messages: {e}", level="warning")
            
            unread_count = 0
            try:
                unread_count = get_unread_count(moniker, database=self.args.databasename)
            except Exception as e:
                io.echo(f"Failed to get unread count: {e}", level="warning")
            
            return {
                "type": "auth_result",
                "success": True,
                "moniker": moniker,
                "balance": balance,
                "message": "Authenticated",
                "pending_messages": pending_messages,
                "unread_count": unread_count,
            }
        else:
            return {
                "type": "auth_result",
                "success": False,
                "moniker": moniker,
                "balance": 0,
                "message": result["message"],
            }





class TableServiceHandler(BaseService):
    """Handle table management messages."""
    
    from casino.services.table import TableService
    
    def __init__(self, args: Any, session_manager: SessionManager, channel_state: Optional[ChannelState] = None):
        super().__init__(args, session_manager)
        self.table_service = self.TableService(args)
        self.channel_state = channel_state
    
    async def handle_message(
        self, server: Any, websocket: Any, path: str, message: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        msg_type = message.get("type")
        
        if msg_type == "list_tables":
            return await self._handle_list_tables(id(websocket), message)
        elif msg_type == "create_table":
            return await self._handle_create_table(id(websocket), message)
        elif msg_type == "join_table":
            return await self._handle_join_table(id(websocket), message)
        elif msg_type == "leave_table":
            return await self._handle_leave_table(id(websocket), message)
        elif msg_type == "watch_table":
            return await self._handle_watch_table(id(websocket), message)
        elif msg_type == "stop_watching":
            return await self._handle_stop_watching(id(websocket), message)
        elif msg_type == "update_table":
            return await self._handle_update_table(id(websocket), message)
        elif msg_type == "kick_player":
            return await self._handle_kick_player(id(websocket), message)
        
        return None
    
    async def _handle_list_tables(self, session_id: int, message: Dict[str, Any]) -> Dict[str, Any]:
        game_type = message.get("game_type")
        is_sysop = self.sessions.get_is_sysop(session_id)
        tables = self.table_service.list_tables(game_type, is_sysop=is_sysop)
        return {"type": "table_list", "tables": tables}

    async def _handle_create_table(self, session_id: int, message: Dict[str, Any]) -> Dict[str, Any]:
        session_moniker = self.sessions.get_moniker(session_id)
        if not session_moniker:
            return {"type": "error", "code": "not_authenticated"}

        game_type = message.get("game_type", "blackjack")
        min_bet = message.get("min_bet", 10)
        max_bet = message.get("max_bet", 1000)
        table_moniker = message.get("moniker") or None
        hidden = bool(message.get("hidden", False))

        result = self.table_service.create_table(
            game_type, session_moniker, min_bet, max_bet, table_moniker, hidden=hidden
        )

        if result["success"]:
            return {
                "type": "table_created",
                "moniker": result["table"]["moniker"],
                "location": result["table"]["location"],
                "hidden": result["table"].get("hidden", False),
                "message": result["message"],
            }
        else:
            return {"type": "error", "code": "create_failed", "message": result["message"]}

    async def _handle_update_table(self, session_id: int, message: Dict[str, Any]) -> Dict[str, Any]:
        session_moniker = self.sessions.get_moniker(session_id)
        if not session_moniker:
            return {"type": "error", "code": "not_authenticated"}

        is_sysop = self.sessions.get_is_sysop(session_id)

        table_moniker = message.get("moniker")
        if not table_moniker:
            return {"type": "error", "code": "invalid_request", "message": "moniker required"}

        updates = {}
        if "new_moniker" in message:
            updates["new_moniker"] = message["new_moniker"]
        if "min_bet" in message:
            updates["minimumbet"] = message["min_bet"]
        if "max_bet" in message:
            updates["maximumbet"] = message["max_bet"]
        if "status" in message:
            updates["status"] = message["status"]
        if "hidden" in message:
            updates["hidden"] = bool(message["hidden"])

        if not updates:
            return {"type": "error", "code": "invalid_request", "message": "No fields to update"}

        result = self.table_service.update_table(
            table_moniker, session_moniker, is_sysop=is_sysop, **updates
        )

        if result["success"]:
            return {
                "type": "table_updated",
                "moniker": result["table"]["moniker"],
                "hidden": result["table"].get("hidden", False),
                "message": result["message"],
            }
        else:
            return {"type": "error", "code": "update_failed", "message": result["message"]}

    async def _handle_join_table(self, session_id: int, message: Dict[str, Any]) -> Dict[str, Any]:
        session_moniker = self.sessions.get_moniker(session_id)
        if not session_moniker:
            return {"type": "error", "code": "not_authenticated"}

        table_moniker = message.get("moniker")

        if not table_moniker:
            return {"type": "error", "code": "invalid_request", "message": "moniker required"}

        is_sysop = self.sessions.get_is_sysop(session_id)

        # Slots v1 single-seater invariant: a slots table holds at most
        # one seated player. Spectators can watch via `watch_table` but
        # cannot take a second seat. Multi-player is v2.
        from casino.dal import table as dal_table_join
        table = dal_table_join.get_table(self.args, table_moniker)
        if table and table.get("type") == "slots":
            try:
                with database.connect(self.args) as conn:
                    with database.cursor(conn) as cur:
                        cur.execute(
                            database.query(
                                "SELECT COUNT(DISTINCT playermoniker) AS n "
                                "FROM $casino.map_cardtable_player "
                                "WHERE cardtablemoniker = :m",
                                m=table_moniker,
                            )
                        )
                        row = cur.fetchone()
                        if row and int(row["n"]) >= 1:
                            return {
                                "type": "error",
                                "code": "join_failed",
                                "message": "Slots tables have a single seat; "
                                           "another player is already seated",
                            }
            except Exception as e:
                io.echo(f"slots single-seater check failed: {e}", level="warning")

        result = self.table_service.join_table(
            moniker=table_moniker,
            player_moniker=session_moniker,
            is_sysop=is_sysop,
        )

        if result["success"]:
            self.sessions.set_table_moniker(session_id, table_moniker)

            # Auto-subscribe to table channel for real-time updates
            if self.channel_state:
                channel_subscribe(self.channel_state, session_id, f"casino:table:{table_moniker}")

            return {
                "type": "joined_table",
                "moniker": result["moniker"],
                "message": result["message"],
            }
        else:
            return {"type": "error", "code": "join_failed", "message": result["message"]}
    
    async def _handle_leave_table(self, session_id: int, message: Dict[str, Any]) -> Dict[str, Any]:
        session_moniker = self.sessions.get_moniker(session_id)
        if not session_moniker:
            return {"type": "error", "code": "not_authenticated"}
        
        table_moniker = message.get("moniker") or self.sessions.get_table_moniker(session_id)
        
        if not table_moniker:
            return {"type": "error", "code": "not_at_table"}
        
        result = self.table_service.leave_table(table_moniker, session_moniker)
        
        if result["success"]:
            self.sessions.set_table_moniker(session_id, None)
            # Unsubscribe from table channel
            if self.channel_state:
                channel_unsubscribe(self.channel_state, session_id, f"casino:table:{table_moniker}")
        
        return {
            "type": "left_table",
            "moniker": table_moniker,
            "message": result["message"],
        }
    
    async def _handle_kick_player(self, session_id: int, message: Dict[str, Any]) -> Dict[str, Any]:
        session_moniker = self.sessions.get_moniker(session_id)
        if not session_moniker:
            return {"type": "error", "code": "not_authenticated"}
        
        is_sysop = self.sessions.get_is_sysop(session_id)
        
        table_monikers = message.get("table_monikers", [])
        player_moniker = message.get("player_moniker", "").strip()
        
        if not player_moniker:
            return {"type": "error", "code": "invalid_request", "message": "player_moniker required"}
        
        if not table_monikers:
            return {"type": "error", "code": "invalid_request", "message": "table_monikers required"}
        
        if "all" in [t.lower() for t in table_monikers]:
            table_monikers = await async_dal_table.get_player_tables(self.args, player_moniker)
        
        kicked_tables = []
        errors = []
        
        for table_moniker in table_monikers:
            table = await async_dal_table.get_table(self.args, table_moniker)
            if not table:
                errors.append(f"Table not found: {table_moniker}")
                continue
            
            if not is_sysop and table.get("ownermoniker") != session_moniker:
                errors.append(f"Permission denied for table: {table_moniker}")
                continue
            
            removed = await async_dal_table.remove_player_from_table(self.args, table_moniker, player_moniker)
            if removed:
                kicked_tables.append(table_moniker)
                try:
                    notify_send(
                        notification_type="casino_kick",
                        recipients=[player_moniker],
                        template="You have been kicked from table {table_moniker} by {admin_moniker}",
                        template_vars={"table_moniker": table_moniker, "admin_moniker": session_moniker},
                        sender_moniker=session_moniker,
                        urgency=NotificationUrgency.IMPORTANT,
                        args=self.args,
                    )
                except Exception as e:
                    errors.append(f"Failed to notify player for {table_moniker}: {str(e)}")
            else:
                errors.append(f"Player not at table: {table_moniker}")
        
        if kicked_tables:
            return {
                "type": "player_kicked",
                "player_moniker": player_moniker,
                "tables": kicked_tables,
                "message": f"Kicked {player_moniker} from {len(kicked_tables)} table(s)",
            }
        else:
            return {
                "type": "error",
                "code": "kick_failed",
                "message": "; ".join(errors) if errors else "Player not found at any specified table",
            }
    
    async def _handle_watch_table(self, session_id: int, message: Dict[str, Any]) -> Dict[str, Any]:
        table_moniker = message.get("moniker")
        
        if not table_moniker:
            return {"type": "error", "code": "invalid_request", "message": "moniker required"}
        
        try:
            table = await async_dal_table.get_table(self.args, table_moniker)
        except Exception as e:
            io.echo(f"_handle_watch_table error: {e}", level="error")
            return {"type": "error", "code": "service_error", "message": str(e)}
        
        if not table:
            return {"type": "error", "code": "invalid_request", "message": "Table not found"}
        
        self.sessions.add_spectator(table_moniker, session_id)
        
        # Auto-subscribe to table channel for real-time updates
        if self.channel_state:
            channel_subscribe(self.channel_state, session_id, f"casino:table:{table_moniker}")
        
        return {
            "type": "watching_table",
            "moniker": table_moniker,
            "message": f"Now watching table {table_moniker}",
        }
    
    async def _handle_stop_watching(self, session_id: int, message: Dict[str, Any]) -> Dict[str, Any]:
        table_moniker = message.get("moniker")
        if table_moniker:
            self.sessions.remove_spectator(table_moniker, session_id)
            # Unsubscribe from table channel
            if self.channel_state:
                channel_unsubscribe(self.channel_state, session_id, f"casino:table:{table_moniker}")
        
        return {"type": "stopped_watching", "message": "Stopped watching"}


class GameServiceHandler(BaseService):
    """Handle game messages."""
    
    from casino.services.game import GameService
    
    def __init__(self, args: Any, session_manager: SessionManager):
        super().__init__(args, session_manager)
        self.game_service = self.GameService(args)
    
    async def handle_message(
        self, server: Any, websocket: Any, path: str, message: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        msg_type = message.get("type")
        
        if msg_type in ("hit", "stand", "double", "split", "surrender"):
            return await self._handle_game_action(id(websocket), msg_type, message, server)
        
        return None
    
    async def _handle_game_action(self, session_id: int, action: str, message: Optional[Dict[str, Any]] = None, server: Optional[Any] = None) -> Optional[Dict[str, Any]]:
        moniker = self.sessions.get_moniker(session_id)
        if not moniker:
            return {"type": "error", "code": "not_authenticated"}
        
        table_moniker = self.sessions.get_table_moniker(session_id)
        io.echo(f"_handle_game_action: action={action}, session_id={session_id}, table_moniker={table_moniker}", level="info")
        if not table_moniker:
            return {"type": "error", "code": "not_at_table"}
        
        if action == "bet":
            return {"type": "error", "code": "invalid_request", "message": "Use bet message with amount"}
        
        result = None
        if action == "hit":
            result = self.game_service.hit(table_moniker, moniker)
        elif action == "stand":
            result = self.game_service.stand(table_moniker, moniker)
            self.game_service.settle_game(table_moniker)
        elif action == "double":
            hand_id = message.get("hand_id") if message else None
            result = self.game_service.double(table_moniker, moniker, hand_id)
            self.game_service.settle_game(table_moniker)
        elif action == "split":
            hand_id = message.get("hand_id") if message else None
            result = self.game_service.split(table_moniker, moniker, hand_id)
        elif action == "surrender":
            result = self.game_service.surrender(table_moniker, moniker)
            if result and result.get("success"):
                self.game_service.settle_game(table_moniker)
        
        if result and not result.get("success", True):
            return {"type": "error", "code": "action_failed", "message": result.get("message", "")}
        
        # Return game state directly to player
        game_state = self.game_service.get_game_state(table_moniker, moniker)
        game_state["type"] = "game_state"
        
        # Broadcast game_state to all at the table (including spectators)
        if server and table_moniker:
            broadcast_state = self.game_service.get_game_state(table_moniker, "")
            broadcast_state["type"] = "game_state"
            observer_count = len(self.sessions.get_table_observers(table_moniker))
            player_count = self.sessions.get_table_player_count(table_moniker)
            io.echo(
                f"broadcast game_state: channel=casino:table:{table_moniker} "
                f"phase={broadcast_state.get('phase', '?')} "
                f"players={player_count} observers={observer_count}",
                level="info",
            )
            await server.publish(f"casino:table:{table_moniker}", broadcast_state)

        return game_state


class BetServiceHandler(BaseService):
    """Handle bet messages."""
    
    from casino.services.game import GameService
    
    def __init__(self, args: Any, session_manager: SessionManager):
        super().__init__(args, session_manager)
        self.game_service = self.GameService(args)
    
    async def handle_message(
        self, server: Any, websocket: Any, path: str, message: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        msg_type = message.get("type")
        
        if msg_type == "bet":
            return await self._handle_bet(id(websocket), message, server)
        
        return None
    
    async def _handle_bet(self, session_id: int, message: Dict[str, Any], server: Optional[Any] = None) -> Optional[Dict[str, Any]]:
        moniker = self.sessions.get_moniker(session_id)
        if not moniker:
            return {"type": "error", "code": "not_authenticated"}
        
        table_moniker = self.sessions.get_table_moniker(session_id)
        io.echo(f"_handle_bet: session_id={session_id}, moniker={moniker}, table_moniker={table_moniker}", level="info")
        if not table_moniker:
            return {"type": "error", "code": "not_at_table"}
        
        amount = message.get("amount", 0)
        
        if not isinstance(amount, int) or amount <= 0:
            io.echo(
                f"_handle_bet: WARNING: Invalid bet attempt from {moniker} at {table_moniker}: "
                f"amount={amount!r} (type={type(amount).__name__})",
                level="warning"
            )
            return {"type": "error", "code": "invalid_bet", "message": "Bet amount must be a positive integer"}
        
        io.echo(f"_handle_bet: {moniker} betting {amount} at {table_moniker}", level="info")
        
        result = self.game_service.place_bet(table_moniker, moniker, amount)
        
        if result.get("success"):
            game_state = self.game_service.get_game_state(table_moniker, moniker)
            game_state["type"] = "game_state"
            io.echo(f"_handle_bet: SUCCESS: {moniker} bet {amount} at {table_moniker}", level="info")
            
            # Broadcast game_state to all at the table (including spectators)
            if server and table_moniker:
                broadcast_state = self.game_service.get_game_state(table_moniker, "")
                broadcast_state["type"] = "game_state"
                observer_count = len(self.sessions.get_table_observers(table_moniker))
                player_count = self.sessions.get_table_player_count(table_moniker)
                io.echo(
                    f"broadcast game_state: channel=casino:table:{table_moniker} "
                    f"phase={broadcast_state.get('phase', '?')} "
                    f"players={player_count} observers={observer_count}",
                    level="info",
                )
                await server.publish(f"casino:table:{table_moniker}", broadcast_state)

            return game_state
        else:
            error_msg = result.get("message", "")
            io.echo(
                f"_handle_bet: FAILED: {moniker} bet {amount} at {table_moniker}: {error_msg}",
                level="warning"
            )
            return {"type": "error", "code": "bet_failed", "message": error_msg}


class ChatServiceHandler(BaseService):
    """Handle chat messages."""
    
    async def handle_message(
        self, server: Any, websocket: Any, path: str, message: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        msg_type = message.get("type")
        
        if msg_type in ("chat_table", "chat_global", "emote"):
            return await self._handle_chat(id(websocket), msg_type, message)
        
        return None
    
    async def _handle_chat(
        self, session_id: int, msg_type: str, message: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        moniker = self.sessions.get_moniker(session_id)
        if not moniker:
            return {"type": "error", "code": "not_authenticated"}
        
        chat_msg = message.get("message", "")
        
        if msg_type == "chat_table":
            table_moniker = self.sessions.get_table_moniker(session_id)
            if not table_moniker:
                return {"type": "error", "code": "not_at_table"}
            
            return {
                "type": "chat_message",
                "from_moniker": moniker,
                "message": chat_msg,
                "scope": "table",
                "moniker": table_moniker,
                "timestamp": datetime.utcnow().isoformat(),
            }
        
        elif msg_type == "chat_global":
            return {
                "type": "chat_message",
                "from_moniker": moniker,
                "message": chat_msg,
                "scope": "global",
                "timestamp": datetime.utcnow().isoformat(),
            }
        
        elif msg_type == "emote":
            table_moniker = self.sessions.get_table_moniker(session_id)
            return {
                "type": "chat_message",
                "from_moniker": moniker,
                "message": chat_msg,
                "scope": "table" if table_moniker else "global",
                "moniker": table_moniker,
                "timestamp": datetime.utcnow().isoformat(),
            }
        
        return None


class SlotServiceHandler(BaseService):
    """Handle slot machine messages.

    Message types:
    - ``slot_spin``   - client request: spin the reels
    - ``slot_paytable`` - client request: get the table's paytable
    - ``slot_history``  - client request: get the player's recent spins
    """

    def __init__(self, args: Any, session_manager: SessionManager, channel_state: Optional[ChannelState] = None):
        super().__init__(args, session_manager)
        self.channel_state = channel_state
        from casino.services.slots import (
            handle_spin as _handle_spin,
            handle_get_paytable as _handle_paytable,
            handle_get_history as _handle_history,
        )
        self._handle_spin = _handle_spin
        self._handle_paytable = _handle_paytable
        self._handle_history = _handle_history

    async def handle_message(
        self, server: Any, websocket: Any, path: str, message: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        msg_type = message.get("type")
        if msg_type == "slot_spin":
            return await self._handle_spin_msg(id(websocket), message, server)
        if msg_type == "slot_paytable":
            return await self._handle_paytable_msg(id(websocket), message)
        if msg_type == "slot_history":
            return await self._handle_history_msg(id(websocket), message)
        return None

    async def _handle_spin_msg(
        self,
        session_id: int,
        message: Dict[str, Any],
        server: Optional[Any] = None,
    ) -> Dict[str, Any]:
        moniker = self.sessions.get_moniker(session_id)
        if not moniker:
            return {"type": "error", "code": "not_authenticated"}

        bet = message.get("bet", 0)
        table_moniker = message.get("table_moniker") or self.sessions.get_table_moniker(session_id)
        if not table_moniker:
            return {"type": "error", "code": "not_at_table"}

        result = self._handle_spin(self.args, table_moniker, moniker, bet)

        if not result.get("success"):
            return {
                "type": "error",
                "code": result.get("code", "spin_failed"),
                "message": result.get("message", "Spin failed"),
            }

        spin = result["spin"]
        # Broadcast to spectators at the table
        if server is not None:
            broadcast_msg = {
                "type": "slot_result",
                "table_moniker": table_moniker,
                "player_moniker": moniker,
                "spin": {
                    "id": spin["id"],
                    "bet": spin["bet"],
                    "payout": spin["payout"],
                    "net": spin["net"],
                    "reels": spin["reels"],
                    "center_row": spin["center_row"],
                    "wins": spin["wins"],
                },
            }
            try:
                await server.publish(f"casino:table:{table_moniker}", broadcast_msg)
            except Exception as e:
                io.echo(f"slot broadcast failed: {e}", level="warning")

        return {
            "type": "slot_result",
            "table_moniker": table_moniker,
            "spin": spin,
        }

    async def _handle_paytable_msg(
        self,
        session_id: int,
        message: Dict[str, Any],
    ) -> Dict[str, Any]:
        moniker = self.sessions.get_moniker(session_id)
        if not moniker:
            return {"type": "error", "code": "not_authenticated"}
        table_moniker = message.get("table_moniker") or self.sessions.get_table_moniker(session_id)
        if not table_moniker:
            return {"type": "error", "code": "not_at_table"}
        result = self._handle_paytable(self.args, table_moniker)
        if not result.get("success"):
            return {
                "type": "error",
                "code": result.get("code", "paytable_failed"),
                "message": result.get("message", "Paytable lookup failed"),
            }
        return {
            "type": "slot_paytable",
            "moniker": result["moniker"],
            "payouts": result["payouts"],
        }

    async def _handle_history_msg(
        self,
        session_id: int,
        message: Dict[str, Any],
    ) -> Dict[str, Any]:
        moniker = self.sessions.get_moniker(session_id)
        if not moniker:
            return {"type": "error", "code": "not_authenticated"}
        limit = int(message.get("limit", 50))
        history = self._handle_history(self.args, moniker, limit)
        return {
            "type": "slot_history",
            "spins": history,
        }





class MessageRouter:
    """
    Main message handler that coordinates all services.
    Handles broadcasting and session lifecycle.
    """
    
    def __init__(self, args: Any):
        self.args = args
        self.sessions = CasinoSessionManager()
        
        # Channel subscription state for pub/sub messaging
        self.channel_state = ChannelState()
        
        # Create services
        self.auth_service = AuthService(args, self.sessions, self.channel_state)
        self.table_service = TableServiceHandler(args, self.sessions, self.channel_state)
        self.game_service = GameServiceHandler(args, self.sessions)
        self.bet_service = BetServiceHandler(args, self.sessions)
        self.chat_service = ChatServiceHandler(args, self.sessions)
        self.slot_service = SlotServiceHandler(args, self.sessions, self.channel_state)
        self.yahtzee_service_handler = YahtzeeServiceHandler(args, self.sessions)
        self.tictactoe_service_handler = TictactoeServiceHandler(args, self.sessions)
    
    def register_all(self, server: Any) -> None:
        """Register all services with the WebSocketServer."""
        server.register_service(self.auth_service, ["auth", "ping"])
        server.register_service(self.table_service, [
            "list_tables", "create_table", "update_table", "join_table", "leave_table",
            "watch_table", "stop_watching"
        ])
        server.register_service(self.game_service, ["hit", "stand", "double", "split", "surrender"])
        server.register_service(self.bet_service, ["bet"])
        server.register_service(self.chat_service, ["chat_table", "chat_global", "emote"])

        # Register slot service for slot machine play
        server.register_service(self.slot_service, [
            "slot_spin", "slot_paytable", "slot_history"
        ])

        # Register yahtzee service for dice play
        server.register_service(self.yahtzee_service_handler, [
            "yahtzee_quick_play", "yahtzee_roll", "yahtzee_reroll", "yahtzee_score"
        ])

        # Register tictactoe service for board play
        server.register_service(self.tictactoe_service_handler, [
            "tictactoe_quick_play", "tictactoe_move",
            "tictactoe_resign", "tictactoe_join"
        ])
    
    async def handle_broadcast(
        self, server: Any, websocket: Any, path: str, message: Dict[str, Any]
    ) -> None:
        """Handle message that should be broadcast."""
        msg_type = message.get("type")
        
        if msg_type == "chat_message":
            scope = message.get("scope", "global")
            table_moniker = message.get("moniker")
            
            if scope == "table" and table_moniker:
                await server.publish(f"casino:table:{table_moniker}", message)
            else:
                await server.publish("casino:global", message)
        
        elif msg_type == "game_state":
            table_moniker = message.get("moniker")
            if table_moniker:
                await server.publish(f"casino:table:{table_moniker}", message)
    
    def unregister_session(self, session_id: int) -> None:
        """Clean up session on disconnect."""
        # If the player had a yahtzee game in progress, settle it as
        # a loss so the bet row doesn't stay 'pending' forever.
        table_moniker = self.sessions.get_table_moniker(session_id)
        if table_moniker:
            self.yahtzee_service_handler.finalize_on_disconnect(table_moniker)
            leaving_moniker = self.sessions.get_moniker(session_id)
            self.tictactoe_service_handler.finalize_on_disconnect(
                table_moniker, leaving_moniker
            )
        # Unsubscribe from all channels
        channel_unsubscribe_all(self.channel_state, session_id)
        self.sessions.unregister_session(session_id)


# Backwards compatibility - keep the old MessageHandler class
class MessageHandler(MessageRouter):
    """Legacy MessageHandler for backwards compatibility."""
    
    def __init__(self, args: Any):
        super().__init__(args)
        
        # Legacy interface - expose underlying services
        self.player_service = self.auth_service.player_service
        self.table_service_obj = self.table_service.table_service
        self.game_service_obj = self.game_service.game_service
    
    async def handle_message(
        self, server: Any, websocket: Any, path: str, message: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Handle message - dispatches to services."""
        msg_type = message.get("type")
        session_id = id(websocket)
        
        # Check authentication for protected commands
        auth_required = msg_type not in ("auth", "ping", "list_tables")
        if auth_required and not self.sessions.get_moniker(session_id):
            return {"type": "error", "code": "not_authenticated", "message": "Not authenticated"}
        
        # Use dispatch via server
        response = await server.dispatch_message(websocket, path, message)
        
        # Handle broadcasting
        if response is None:
            await self.handle_broadcast(server, websocket, path, message)
        
        return response
