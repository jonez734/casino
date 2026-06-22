# casino/api/handler.py
# WebSocket message handler - routes messages to services using bbsengine6.net service registry

from datetime import datetime
from typing import Any, Dict, Optional

from bbsengine6 import io, member
from casino.dal import table as dal_table


class SessionManager:
    """Manages WebSocket sessions and authentication state."""
    
    def __init__(self):
        # {session_id: {"moniker": str, "table_moniker": Optional[str]}}
        self._sessions: Dict[int, Dict[str, Any]] = {}
        
        # Track spectators: table_moniker -> set of session_ids
        self._spectators: Dict[str, set] = {}
    
    def register_session(self, session_id: int, moniker: str, is_sysop: bool = False) -> None:
        self._sessions[session_id] = {"moniker": moniker, "table_moniker": None, "is_sysop": is_sysop}
    
    def unregister_session(self, session_id: int) -> None:
        if session_id in self._sessions:
            table_moniker = self._sessions[session_id].get("table_moniker")
            if table_moniker and table_moniker in self._spectators:
                self._spectators[table_moniker].discard(session_id)
            del self._sessions[session_id]
    
    def get_session(self, session_id: int) -> Optional[Dict[str, Any]]:
        return self._sessions.get(session_id)
    
    def get_moniker(self, session_id: int) -> Optional[str]:
        session = self._sessions.get(session_id)
        return session.get("moniker") if session else None
    
    def get_table_moniker(self, session_id: int) -> Optional[str]:
        session = self._sessions.get(session_id)
        return session.get("table_moniker") if session else None
    
    def set_table_moniker(self, session_id: int, table_moniker: Optional[str]) -> None:
        io.echo(f"set_table_moniker: session_id={session_id}, table_moniker={table_moniker}", level="info")
        if session_id in self._sessions:
            self._sessions[session_id]["table_moniker"] = table_moniker
        else:
            io.echo(f"set_table_moniker: session {session_id} not found in sessions", level="warning")
    
    def get_is_sysop(self, session_id: int) -> bool:
        session = self._sessions.get(session_id)
        return session.get("is_sysop", False) if session else False
    
    def add_spectator(self, table_moniker: str, session_id: int) -> None:
        if table_moniker not in self._spectators:
            self._spectators[table_moniker] = set()
        self._spectators[table_moniker].add(session_id)
    
    def remove_spectator(self, table_moniker: str, session_id: int) -> None:
        if table_moniker in self._spectators:
            self._spectators[table_moniker].discard(session_id)
    
    def get_table_observers(self, table_moniker: str) -> set:
        return self._spectators.get(table_moniker, set())


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
    
    def __init__(self, args: Any, session_manager: SessionManager):
        super().__init__(args, session_manager)
        self.player_service = self.PlayerService(args)
    
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
        
        # Note: Allowing empty passwords for now - some members may have empty passwords
        # TODO: Require password after members set one via BBS
        if not moniker:
            return {"type": "error", "code": "invalid_credentials", "message": "Moniker and password required"}
        
        result = self.player_service.authenticate(moniker, password)
        
        if result["success"]:
            session_id = id(websocket)
            is_sysop = member.issysop(self.args, moniker=moniker) is True
            self.sessions.register_session(session_id, moniker, is_sysop=is_sysop)
            balance = self.player_service.get_balance(moniker)
            return {
                "type": "auth_result",
                "success": True,
                "moniker": moniker,
                "balance": balance,
                "message": "Authenticated",
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
    
    def __init__(self, args: Any, session_manager: SessionManager):
        super().__init__(args, session_manager)
        self.table_service = self.TableService(args)
    
    async def handle_message(
        self, server: Any, websocket: Any, path: str, message: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        msg_type = message.get("type")
        
        if msg_type == "list_tables":
            return await self._handle_list_tables(message)
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
        
        return None
    
    async def _handle_list_tables(self, message: Dict[str, Any]) -> Dict[str, Any]:
        game_type = message.get("game_type")
        tables = self.table_service.list_tables(game_type)
        return {"type": "table_list", "tables": tables}
    
    async def _handle_create_table(self, session_id: int, message: Dict[str, Any]) -> Dict[str, Any]:
        session_moniker = self.sessions.get_moniker(session_id)
        if not session_moniker:
            return {"type": "error", "code": "not_authenticated"}
        
        game_type = message.get("game_type", "blackjack")
        min_bet = message.get("min_bet", 10)
        max_bet = message.get("max_bet", 1000)
        table_moniker = message.get("moniker") or None
        
        result = self.table_service.create_table(game_type, session_moniker, min_bet, max_bet, table_moniker)
        
        if result["success"]:
            return {
                "type": "table_created",
                "moniker": result["table"]["moniker"],
                "location": result["table"]["location"],
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
        
        if not updates:
            return {"type": "error", "code": "invalid_request", "message": "No fields to update"}
        
        result = self.table_service.update_table(
            table_moniker, session_moniker, is_sysop=is_sysop, **updates
        )
        
        if result["success"]:
            return {
                "type": "table_updated",
                "moniker": result["table"]["moniker"],
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
        
        result = self.table_service.join_table(
            moniker=table_moniker,
            player_moniker=session_moniker,
        )
        
        if result["success"]:
            self.sessions.set_table_moniker(session_id, table_moniker)
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
        
        return {
            "type": "left_table",
            "moniker": table_moniker,
            "message": result["message"],
        }
    
    async def _handle_watch_table(self, session_id: int, message: Dict[str, Any]) -> Dict[str, Any]:
        table_moniker = message.get("moniker")
        
        if not table_moniker:
            return {"type": "error", "code": "invalid_request", "message": "moniker required"}
        
        table = dal_table.get_table(self.args, table_moniker)
        if not table:
            return {"type": "error", "code": "invalid_request", "message": "Table not found"}
        
        self.sessions.add_spectator(table_moniker, session_id)
        
        return {
            "type": "watching_table",
            "moniker": table_moniker,
            "message": f"Now watching table {table_moniker}",
        }
    
    async def _handle_stop_watching(self, session_id: int, message: Dict[str, Any]) -> Dict[str, Any]:
        table_moniker = message.get("moniker")
        if table_moniker:
            self.sessions.remove_spectator(table_moniker, session_id)
        
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
        
        if msg_type in ("hit", "stand", "double", "split"):
            return await self._handle_game_action(id(websocket), msg_type)
        
        return None
    
    async def _handle_game_action(self, session_id: int, action: str) -> Optional[Dict[str, Any]]:
        moniker = self.sessions.get_moniker(session_id)
        if not moniker:
            return {"type": "error", "code": "not_authenticated"}
        
        table_moniker = self.sessions.get_table_moniker(session_id)
        io.echo(f"_handle_game_action: action={action}, session_id={session_id}, table_moniker={table_moniker}", level="info")
        if not table_moniker:
            return {"type": "error", "code": "not_at_table"}
        
        # Get message from server's pending message store if needed
        # For now, just handle the action
        
        if action == "bet":
            # Need amount - this would come from a separate message
            # For now, return error asking for amount
            return {"type": "error", "code": "invalid_request", "message": "Use bet message with amount"}
        
        result = None
        if action == "hit":
            result = self.game_service.hit(table_moniker, moniker)
        elif action == "stand":
            result = self.game_service.stand(table_moniker, moniker)
            # Settle game after stand
            self.game_service.settle_game(table_moniker)
        
        if result and not result.get("success", True):
            return {"type": "error", "code": "action_failed", "message": result.get("message", "")}
        
        # Return game state directly to player
        game_state = self.game_service.get_game_state(table_moniker, moniker)
        game_state["type"] = "game_state"
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
            return await self._handle_bet(id(websocket), message)
        
        return None
    
    async def _handle_bet(self, session_id: int, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        moniker = self.sessions.get_moniker(session_id)
        if not moniker:
            return {"type": "error", "code": "not_authenticated"}
        
        table_moniker = self.sessions.get_table_moniker(session_id)
        io.echo(f"_handle_bet: session_id={session_id}, moniker={moniker}, table_moniker={table_moniker}", level="info")
        if not table_moniker:
            return {"type": "error", "code": "not_at_table"}
        
        amount = message.get("amount", 0)
        if amount <= 0:
            return {"type": "error", "code": "invalid_bet", "message": "Bet amount must be positive"}
        
        result = self.game_service.place_bet(table_moniker, moniker, amount)
        
        if result.get("success"):
            # Return game state directly to the player
            game_state = self.game_service.get_game_state(table_moniker, moniker)
            game_state["type"] = "game_state"
            return game_state
        else:
            return {"type": "error", "code": "bet_failed", "message": result.get("message", "")}


class ChatServiceHandler(BaseService):
    """Handle chat messages."""
    
    async def handle_message(
        self, server: Any, websocket: Any, path: str, message: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        msg_type = message.get("type")
        
        if msg_type in ("chat_table", "chat_global", "emote"):
            return await self._handle_chat(id(websocket), msg_type, message)
        
        return None


class BankServiceHandler(BaseService):
    """Handle bank management messages."""
    
    from casino.services.bank import BankService
    
    def __init__(self, args: Any, session_manager: SessionManager):
        super().__init__(args, session_manager)
        self.bank_service = self.BankService(args)
    
    async def handle_message(
        self, server: Any, websocket: Any, path: str, message: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        msg_type = message.get("type")
        
        if msg_type == "bank_balance":
            return await self._handle_balance(id(websocket), message)
        elif msg_type == "bank_add":
            return await self._handle_add(id(websocket), message)
        elif msg_type == "bank_remove":
            return await self._handle_remove(id(websocket), message)
        elif msg_type == "bank_transfer_request":
            return await self._handle_transfer_request(id(websocket), message)
        elif msg_type == "bank_transfer_approve":
            return await self._handle_transfer_approve(id(websocket), message)
        elif msg_type == "bank_transfer_reject":
            return await self._handle_transfer_reject(id(websocket), message)
        elif msg_type == "bank_pending":
            return await self._handle_pending(id(websocket), message)
        elif msg_type == "bank_history":
            return await self._handle_history(id(websocket), message)
        elif msg_type == "bank_list_all":
            return await self._handle_list_all(id(websocket), message)
        
        return None
    
    def _check_permission(self, session_id: int, table_moniker: str) -> Dict[str, Any]:
        """Check if session can manage this table."""
        session = self.sessions.get_session(session_id)
        if not session:
            return {"allowed": False, "message": "Not authenticated"}
        
        moniker = session.get("moniker", "")
        is_sysop = session.get("is_sysop", False)
        
        if self.bank_service.can_manage(table_moniker, moniker, is_sysop):
            return {"allowed": True, "moniker": moniker, "is_sysop": is_sysop}
        
        return {"allowed": False, "message": f"You don't have permission to manage table {table_moniker}"}
    
    async def _handle_balance(self, session_id: int, message: Dict[str, Any]) -> Dict[str, Any]:
        session = self.sessions.get_session(session_id)
        if not session:
            return {"type": "error", "code": "not_authenticated"}
        
        table_moniker = message.get("moniker")
        if not table_moniker:
            return {"type": "error", "code": "invalid_request", "message": "moniker required"}
        
        perm = self._check_permission(session_id, table_moniker)
        if not perm["allowed"]:
            return {"type": "error", "code": "permission_denied", "message": perm["message"]}
        
        balance = self.bank_service.get_balance(table_moniker)
        table = self.bank_service.get_table(table_moniker)
        
        return {
            "type": "bank_balance",
            "moniker": table_moniker,
            "balance": balance,
            "max_transfer": int(table.get("maxtransfer", 1000)) if table else 1000,
        }
    
    async def _handle_add(self, session_id: int, message: Dict[str, Any]) -> Dict[str, Any]:
        session = self.sessions.get_session(session_id)
        if not session:
            return {"type": "error", "code": "not_authenticated"}
        
        table_moniker = message.get("moniker")
        if not table_moniker:
            return {"type": "error", "code": "invalid_request", "message": "moniker required"}
        
        perm = self._check_permission(session_id, table_moniker)
        if not perm["allowed"]:
            return {"type": "error", "code": "permission_denied", "message": perm["message"]}
        
        amount = message.get("amount", 0)
        source = message.get("source", "house")
        description = message.get("description", "")
        
        result = self.bank_service.add_funds(
            table_moniker, amount, source,
            member_moniker=session["moniker"],
            description=description,
        )
        
        if result["success"]:
            return {
                "type": "bank_added",
                "moniker": table_moniker,
                "amount": amount,
                "new_balance": result["new_balance"],
                "message": result["message"],
            }
        else:
            return {"type": "error", "code": "add_failed", "message": result["message"]}
    
    async def _handle_remove(self, session_id: int, message: Dict[str, Any]) -> Dict[str, Any]:
        session = self.sessions.get_session(session_id)
        if not session:
            return {"type": "error", "code": "not_authenticated"}
        
        table_moniker = message.get("moniker")
        if not table_moniker:
            return {"type": "error", "code": "invalid_request", "message": "moniker required"}
        
        perm = self._check_permission(session_id, table_moniker)
        if not perm["allowed"]:
            return {"type": "error", "code": "permission_denied", "message": perm["message"]}
        
        amount = message.get("amount", 0)
        reason = message.get("reason", "adjustment")
        description = message.get("description", "")
        
        result = self.bank_service.remove_funds(
            table_moniker, amount, reason,
            member_moniker=session["moniker"],
            description=description,
        )
        
        if result["success"]:
            return {
                "type": "bank_removed",
                "moniker": table_moniker,
                "amount": amount,
                "new_balance": result["new_balance"],
                "message": result["message"],
            }
        else:
            return {"type": "error", "code": "remove_failed", "message": result["message"]}
    
    async def _handle_transfer_request(self, session_id: int, message: Dict[str, Any]) -> Dict[str, Any]:
        session = self.sessions.get_session(session_id)
        if not session:
            return {"type": "error", "code": "not_authenticated"}
        
        from_table = message.get("from_moniker")
        to_table = message.get("to_moniker")
        amount = message.get("amount", 0)
        
        if not from_table or not to_table:
            return {"type": "error", "code": "invalid_request", "message": "Both from_moniker and to_moniker required"}
        
        perm = self._check_permission(session_id, from_table)
        if not perm["allowed"]:
            return {"type": "error", "code": "permission_denied", "message": perm["message"]}
        
        result = self.bank_service.request_transfer(
            from_table, to_table, amount,
            requested_by=session["moniker"],
        )
        
        if result["success"]:
            return {
                "type": "bank_transfer_requested",
                "transfer_id": result.get("transfer_id"),
                "message": result["message"],
            }
        else:
            return {"type": "error", "code": "transfer_failed", "message": result["message"]}
    
    async def _handle_transfer_approve(self, session_id: int, message: Dict[str, Any]) -> Dict[str, Any]:
        session = self.sessions.get_session(session_id)
        if not session:
            return {"type": "error", "code": "not_authenticated"}
        
        transfer_id = message.get("transfer_id")
        if not transfer_id:
            return {"type": "error", "code": "invalid_request", "message": "transfer_id required"}
        
        result = self.bank_service.approve_transfer(transfer_id, session["moniker"])
        
        if result["success"]:
            return {
                "type": "bank_transfer_approved",
                "message": result["message"],
                "from_balance": result.get("from_balance"),
                "to_balance": result.get("to_balance"),
            }
        else:
            return {"type": "error", "code": "approve_failed", "message": result["message"]}
    
    async def _handle_transfer_reject(self, session_id: int, message: Dict[str, Any]) -> Dict[str, Any]:
        session = self.sessions.get_session(session_id)
        if not session:
            return {"type": "error", "code": "not_authenticated"}
        
        transfer_id = message.get("transfer_id")
        if not transfer_id:
            return {"type": "error", "code": "invalid_request", "message": "transfer_id required"}
        
        result = self.bank_service.reject_transfer(transfer_id, session["moniker"])
        
        if result["success"]:
            return {
                "type": "bank_transfer_rejected",
                "message": result["message"],
            }
        else:
            return {"type": "error", "code": "reject_failed", "message": result["message"]}
    
    async def _handle_pending(self, session_id: int, message: Dict[str, Any]) -> Dict[str, Any]:
        session = self.sessions.get_session(session_id)
        if not session:
            return {"type": "error", "code": "not_authenticated"}
        
        table_moniker = message.get("moniker", "")
        is_sysop = session.get("is_sysop", False)
        
        transfers = self.bank_service.list_pending_transfers(table_moniker, is_sysop)
        
        return {
            "type": "bank_pending",
            "transfers": transfers,
        }
    
    async def _handle_history(self, session_id: int, message: Dict[str, Any]) -> Dict[str, Any]:
        session = self.sessions.get_session(session_id)
        if not session:
            return {"type": "error", "code": "not_authenticated"}
        
        table_moniker = message.get("moniker")
        if not table_moniker:
            return {"type": "error", "code": "invalid_request", "message": "moniker required"}
        
        perm = self._check_permission(session_id, table_moniker)
        if not perm["allowed"]:
            return {"type": "error", "code": "permission_denied", "message": perm["message"]}
        
        limit = message.get("limit", 50)
        history = self.bank_service.get_history(table_moniker, limit)
        
        return {
            "type": "bank_history",
            "moniker": table_moniker,
            "transactions": history,
        }
    
    async def _handle_list_all(self, session_id: int, message: Dict[str, Any]) -> Dict[str, Any]:
        session = self.sessions.get_session(session_id)
        if not session:
            return {"type": "error", "code": "not_authenticated"}
        
        if not session.get("is_sysop", False):
            return {"type": "error", "code": "permission_denied", "message": "Sysop only"}
        
        balances = self.bank_service.get_all_balances()
        
        return {
            "type": "bank_list_all",
            "tables": balances,
        }
    
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


class MessageRouter:
    """
    Main message handler that coordinates all services.
    Handles broadcasting and session lifecycle.
    """
    
    def __init__(self, args: Any):
        self.args = args
        self.sessions = SessionManager()
        
        # Create services
        self.auth_service = AuthService(args, self.sessions)
        self.table_service = TableServiceHandler(args, self.sessions)
        self.game_service = GameServiceHandler(args, self.sessions)
        self.bet_service = BetServiceHandler(args, self.sessions)
        self.chat_service = ChatServiceHandler(args, self.sessions)
        self.bank_service = BankServiceHandler(args, self.sessions)
    
    def register_all(self, server: Any) -> None:
        """Register all services with the WebSocketServer."""
        server.register_service(self.auth_service, ["auth", "ping"])
        server.register_service(self.table_service, [
            "list_tables", "create_table", "update_table", "join_table", "leave_table",
            "watch_table", "stop_watching"
        ])
        server.register_service(self.game_service, ["hit", "stand", "double", "split"])
        server.register_service(self.bet_service, ["bet"])
        server.register_service(self.chat_service, ["chat_table", "chat_global", "emote"])
        server.register_service(self.bank_service, [
            "bank_balance", "bank_add", "bank_remove",
            "bank_transfer_request", "bank_transfer_approve", "bank_transfer_reject",
            "bank_pending", "bank_history", "bank_list_all"
        ])
    
    async def handle_broadcast(
        self, server: Any, websocket: Any, path: str, message: Dict[str, Any]
    ) -> None:
        """Handle message that should be broadcast."""
        msg_type = message.get("type")
        
        if msg_type == "chat_message":
            scope = message.get("scope", "global")
            table_id = message.get("table_id")
            
            if scope == "table" and table_id:
                await server.broadcast(message, str(table_id))
            else:
                await server.broadcast(message)
        
        elif msg_type == "game_state":
            table_id = message.get("table_id")
            if table_id:
                await server.broadcast(message, str(table_id))
    
    def unregister_session(self, session_id: int) -> None:
        """Clean up session on disconnect."""
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
