# casino/api/handler.py
# WebSocket message handler - routes messages to services using bbsengine6.net service registry

from datetime import datetime
from typing import Any, Optional

from bbsengine6 import database, io, member
from bbsengine6.message import MessageUrgency as NotificationUrgency
from bbsengine6.message import deliver_pending_on_connect, get_unread_count
from bbsengine6.message import send as notify_send
from bbsengine6.net import (
    ChannelState,
    channel_subscribe,
    channel_unsubscribe,
    channel_unsubscribe_all,
)
from bbsengine6.session import SessionManager

from casino.api._auth import (
    check_access as _check_access_pipeline,
)
from casino.dal.aiosql import table as async_dal_table
from casino.tictactoe.api_handler import TictactoeServiceHandler
from casino.yahtzee.api_handler import YahtzeeServiceHandler


class CasinoSessionManager(SessionManager):
    """Extends base SessionManager with table/spectator tracking.

    Two parallel sources of truth live on each session record:
      - ``table_moniker`` -- the table the player is seated at
        (a player sits at exactly one table, or none).
      - ``spectator_of`` -- the set of tables the session is watching
        without being seated (a session can spectate multiple tables
        concurrently).

    The ``_spectators`` dict is a reverse index keyed by ``table_moniker``
    that maps to the set of session ids currently spectating it. It is
    rebuilt from each session's ``spectator_of`` set on add / remove so
    ``get_table_observers`` is O(1). ``get_table_player_count`` does a
    full scan because there is no player-count index (the result is only
    used for log lines, not for routing).
    """

    def __init__(self):
        super().__init__()
        self._spectators: dict[str, set] = {}

    def register_session(self, session_id: int, moniker: str, is_sysop: bool = False) -> None:
        super().register_session(session_id, moniker, is_sysop)
        self._sessions[session_id]["table_moniker"] = None
        self._sessions[session_id]["spectator_of"] = set()

    def unregister_session(self, session_id: int) -> None:
        if session_id in self._sessions:
            for table in list(self._sessions[session_id].get("spectator_of", set())):
                self._purge_spectator(table, session_id)
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
        if session_id in self._sessions:
            self._sessions[session_id].setdefault("spectator_of", set()).add(table_moniker)
        self._spectators.setdefault(table_moniker, set()).add(session_id)

    def remove_spectator(self, table_moniker: str, session_id: int) -> None:
        if session_id in self._sessions:
            self._sessions[session_id].get("spectator_of", set()).discard(table_moniker)
        self._purge_spectator(table_moniker, session_id)

    def get_table_observers(self, table_moniker: str) -> set:
        return self._spectators.get(table_moniker, set())

    def get_table_player_count(self, table_moniker: str) -> int:
        return sum(1 for s in self._sessions.values() if s.get("table_moniker") == table_moniker)

    def _purge_spectator(self, table_moniker: str, session_id: int) -> None:
        observers = self._spectators.get(table_moniker)
        if observers is not None:
            observers.discard(session_id)
            if not observers:
                self._spectators.pop(table_moniker, None)


class BaseService:
    """Base class for message handlers.

    Each handler carries optional token wiring (``secret`` /
    ``token_store`` / ``instance_id``) so the per-op ``_check_access``
    pipeline can re-verify a bearer token on every call. When the
    wiring is absent the token gates become no-ops and authorization
    falls back to the session attributes (legacy / standalone path).
    """

    def __init__(
        self,
        args: Any,
        session_manager: Any,
        *,
        secret: Optional[bytes] = None,
        token_store: Any = None,
        instance_id: Optional[str] = None,
        clock: Any = None,
    ) -> None:
        self.args = args
        self.sessions = session_manager
        self.secret = bytes(secret) if secret else None
        self.token_store = token_store
        self.instance_id = str(instance_id) if instance_id else None
        self._clock = clock

    def _now(self) -> float:
        """Return the current UNIX timestamp, honoring ``clock`` if set."""
        if self._clock is not None:
            return float(self._clock())
        import time as _time

        return _time.time()

    def _check_access(
        self, websocket: Any, op: str, message: dict[str, Any]
    ) -> tuple[Optional[Any], Optional[dict[str, Any]]]:
        """Run the five access gates for ``op``.

        Returns ``(state, None)`` on allow or ``(state_or_None,
        error_envelope)`` on deny. See ``casino.api._auth.check_access``
        for the gate list. Handlers call this as the first step of
        every per-op ``_handle_*`` method and return the envelope on
        deny.
        """
        return _check_access_pipeline(self, websocket, op, message)

    async def handle_message(
        self, server: Any, websocket: Any, path: str, message: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        raise NotImplementedError


class AuthService(BaseService):
    """Handle authentication messages."""

    from casino.services.player import PlayerService

    def __init__(self, args: Any, session_manager: SessionManager, channel_state: Optional[ChannelState] = None):
        super().__init__(args, session_manager)
        self.player_service = self.PlayerService(args)
        self.channel_state = channel_state

    async def handle_message(
        self, server: Any, websocket: Any, path: str, message: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        msg_type = message.get("type")

        if msg_type == "auth":
            return await self._handle_auth(websocket, message)
        elif msg_type == "ping":
            return {"type": "pong", "timestamp": datetime.utcnow().isoformat()}

        return None

    async def _handle_auth(self, websocket: Any, message: dict[str, Any]) -> dict[str, Any]:
        moniker = message.get("moniker", "")
        password = message.get("password", "")

        if not moniker:
            return {"type": "error", "code": "invalid_credentials", "message": "Moniker and password required"}

        result = self.player_service.authenticate(moniker, password)

        if result["success"]:
            # Prefer the server-assigned ``_bbsengine6_session_id`` so
            # the key matches what every other handler reads via
            # ``_legacy_session_id`` during gameplay (table-moniker
            # lookups, spectator bookkeeping, slot_spin, ...).
            bbs_id = getattr(websocket, "_bbsengine6_session_id", None)
            if bbs_id is not None:
                try:
                    session_id = int(bbs_id)
                except (TypeError, ValueError):
                    session_id = id(websocket)
            else:
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

    def __init__(
        self,
        args: Any,
        session_manager: Any,
        channel_state: Optional[ChannelState] = None,
        *,
        secret: Optional[bytes] = None,
        token_store: Any = None,
        instance_id: Optional[str] = None,
        clock: Any = None,
    ) -> None:
        super().__init__(
            args,
            session_manager,
            secret=secret,
            token_store=token_store,
            instance_id=instance_id,
            clock=clock,
        )
        self.table_service = self.TableService(args)
        self.channel_state = channel_state

    async def handle_message(
        self, server: Any, websocket: Any, path: str, message: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        msg_type = message.get("type")

        if msg_type == "list_tables":
            return await self._handle_list_tables(websocket, message)
        elif msg_type == "create_table":
            return await self._handle_create_table(websocket, message)
        elif msg_type == "join_table":
            return await self._handle_join_table(websocket, message)
        elif msg_type == "leave_table":
            return await self._handle_leave_table(websocket, message)
        elif msg_type == "watch_table":
            return await self._handle_watch_table(websocket, message)
        elif msg_type == "stop_watching":
            return await self._handle_stop_watching(websocket, message)
        elif msg_type == "update_table":
            return await self._handle_update_table(websocket, message)
        elif msg_type == "kick_player":
            return await self._handle_kick_player(websocket, message)

        return None

    def _legacy_session_id(self, websocket: Any) -> int:
        """Return the int key CasinoSessionManager uses for ``websocket``.

        Standalone / door-mode path keeps ``id(websocket)`` so the
        existing spectator / table-moniker bookkeeping continues to
        work. BED-mode (SessionRegistry) ignores this -- it indexes
        by ``str(websocket.id)``.

        Note: ``websocket.id`` on the legacy ``websockets`` library is a
        ``uuid.UUID`` whose ``int()`` coercion yields a 128-bit value
        that is unrelated to the Python object id ``AuthService``
        registered the session under. We deliberately return
        ``id(websocket)`` first so the standalone path stays
        self-consistent; the fallback to ``int(websocket.id)`` only
        fires if the websocket is some odd proxy whose id is already
        an int (e.g. a test double).
        """
        py_id = id(websocket)
        ws_id = getattr(websocket, "id", None)
        if isinstance(ws_id, int) and not isinstance(ws_id, bool):
            return ws_id
        bbs_id = getattr(websocket, "_bbsengine6_session_id", None)
        if bbs_id is not None:
            try:
                return int(bbs_id)
            except (TypeError, ValueError):
                pass
        return py_id

    async def _handle_list_tables(
        self, websocket: Any, message: dict[str, Any]
    ) -> dict[str, Any]:
        state, err = self._check_access(websocket, "list_tables", message)
        if err is not None:
            return err
        game_type = message.get("game_type")
        is_sysop = bool(getattr(state, "is_sysop", False))
        tables = self.table_service.list_tables(game_type, is_sysop=is_sysop)
        return {"type": "table_list", "tables": tables}

    async def _handle_create_table(
        self, websocket: Any, message: dict[str, Any]
    ) -> dict[str, Any]:
        state, err = self._check_access(websocket, "create_table", message)
        if err is not None:
            return err

        game_type = message.get("game_type", "blackjack")
        min_bet = message.get("min_bet", 10)
        max_bet = message.get("max_bet", 1000)
        table_moniker = message.get("moniker") or None
        hidden = bool(message.get("hidden", False))

        result = self.table_service.create_table(
            game_type, state.moniker, min_bet, max_bet, table_moniker, hidden=hidden
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

    async def _handle_update_table(
        self, websocket: Any, message: dict[str, Any]
    ) -> dict[str, Any]:
        state, err = self._check_access(websocket, "update_table", message)
        if err is not None:
            return err

        table_moniker = message.get("moniker")
        if not table_moniker:
            return {"type": "error", "code": "invalid_request", "message": "moniker required"}

        # Resolve the table owner from the DB so ``bbsengine6.casino.access``
        # can compare it against the session moniker for non-sysop ops.
        try:
            owner_table = self.table_service.list_tables(None, is_sysop=True)
            owner = ""
            for t in owner_table or []:
                if t.get("moniker") == table_moniker or t.get("id") == table_moniker:
                    owner = t.get("owner") or t.get("ownermoniker") or ""
                    break
        except Exception:
            owner = ""
        message["owner"] = owner
        message["table_moniker"] = table_moniker

        # Re-run the policy gate now that ``owner`` is populated.
        from casino.access import access as _casino_access

        if not _casino_access(self.args, "update_table", session=state, message=message):
            return {"type": "error", "code": "forbidden", "message": "Operation not permitted for this session"}

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
            table_moniker, state.moniker, is_sysop=bool(state.is_sysop), **updates
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

    async def _handle_join_table(
        self, websocket: Any, message: dict[str, Any]
    ) -> dict[str, Any]:
        state, err = self._check_access(websocket, "join_table", message)
        if err is not None:
            return err

        table_moniker = message.get("moniker")
        if not table_moniker:
            return {"type": "error", "code": "invalid_request", "message": "moniker required"}

        # Slots v1 single-seater invariant: a slots table holds at most
        # one seated player. Spectators can watch via `watch_table` but
        # cannot take a second seat. Multi-player is v2.
        from casino.dal import table as dal_table_join

        table = dal_table_join.get_table(self.args, table_moniker)
        if table and table.get("type") == "slots":
            try:
                with database.connect(self.args) as conn, database.cursor(conn) as cur:
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
                            "message": "Slots tables have a single seat; another player is already seated",
                        }
            except Exception as e:
                io.echo(f"slots single-seater check failed: {e}", level="warning")

        result = self.table_service.join_table(
            moniker=table_moniker,
            player_moniker=state.moniker,
            is_sysop=bool(state.is_sysop),
        )

        if result["success"]:
            self._set_seated(websocket, table_moniker)

            # Auto-subscribe to table channel for real-time updates
            if self.channel_state:
                channel_subscribe(
                    self.channel_state,
                    self._legacy_session_id(websocket),
                    f"casino:table:{table_moniker}",
                )

            return {
                "type": "joined_table",
                "moniker": result["moniker"],
                "message": result["message"],
            }
        else:
            return {"type": "error", "code": "join_failed", "message": result["message"]}

    async def _handle_leave_table(
        self, websocket: Any, message: dict[str, Any]
    ) -> dict[str, Any]:
        state, err = self._check_access(websocket, "leave_table", message)
        if err is not None:
            return err

        table_moniker = message.get("moniker") or self._get_seated(websocket)
        if not table_moniker:
            return {"type": "error", "code": "not_at_table"}

        result = self.table_service.leave_table(table_moniker, state.moniker)

        if result["success"]:
            self._set_seated(websocket, None)
            # Unsubscribe from table channel
            if self.channel_state:
                channel_unsubscribe(
                    self.channel_state,
                    self._legacy_session_id(websocket),
                    f"casino:table:{table_moniker}",
                )

        return {
            "type": "left_table",
            "moniker": table_moniker,
            "message": result["message"],
        }

    async def _handle_kick_player(
        self, websocket: Any, message: dict[str, Any]
    ) -> dict[str, Any]:
        state, err = self._check_access(websocket, "kick_player", message)
        if err is not None:
            return err

        table_monikers = message.get("table_monikers", [])
        player_moniker = (message.get("player_moniker") or "").strip()

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

            message["table_moniker"] = table_moniker
            message["owner"] = table.get("ownermoniker") or ""
            from casino.access import access as _casino_access

            if not _casino_access(
                self.args, "kick_player", session=state, message=message
            ):
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
                        template_vars={"table_moniker": table_moniker, "admin_moniker": state.moniker},
                        sender_moniker=state.moniker,
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

    async def _handle_watch_table(
        self, websocket: Any, message: dict[str, Any]
    ) -> dict[str, Any]:
        state, err = self._check_access(websocket, "watch_table", message)
        if err is not None:
            return err

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

        self._add_spectator(websocket, table_moniker)

        # Auto-subscribe to table channel for real-time updates
        if self.channel_state:
            channel_subscribe(
                self.channel_state,
                self._legacy_session_id(websocket),
                f"casino:table:{table_moniker}",
            )

        return {
            "type": "watching_table",
            "moniker": table_moniker,
            "message": f"Now watching table {table_moniker}",
        }

    async def _handle_stop_watching(
        self, websocket: Any, message: dict[str, Any]
    ) -> dict[str, Any]:
        state, err = self._check_access(websocket, "stop_watching", message)
        if err is not None:
            return err

        table_moniker = message.get("moniker")
        if table_moniker:
            self._remove_spectator(websocket, table_moniker)
            if self.channel_state:
                channel_unsubscribe(
                    self.channel_state,
                    self._legacy_session_id(websocket),
                    f"casino:table:{table_moniker}",
                )

        return {"type": "stopped_watching", "message": "Stopped watching"}

    def _set_seated(self, websocket: Any, table_moniker: Optional[str]) -> None:
        """Mirror ``join_table`` / ``leave_table`` into both session stores."""
        try:
            ws_id = str(websocket.id)
        except Exception:
            ws_id = ""
        sessions = self.sessions
        # BED's SessionRegistry (duck-typed).
        set_tm = getattr(sessions, "set_table_moniker", None)
        if callable(set_tm):
            try:
                state = getattr(sessions, "get_by_websocket", lambda _: None)(ws_id)
                if state is not None:
                    set_tm(state.session_id, table_moniker)
                    return
            except Exception:
                pass
        # CasinoSessionManager (legacy / standalone).
        try:
            sessions.set_table_moniker(self._legacy_session_id(websocket), table_moniker)
        except Exception as e:
            io.echo(f"_set_seated: {e}", level="warning")

    def _get_seated(self, websocket: Any) -> Optional[str]:
        try:
            ws_id = str(websocket.id)
        except Exception:
            ws_id = ""
        sessions = self.sessions
        get_by_websocket = getattr(sessions, "get_by_websocket", None)
        if callable(get_by_websocket):
            try:
                state = get_by_websocket(ws_id)
                if state is not None:
                    return state.table_moniker
            except Exception:
                pass
        try:
            return sessions.get_table_moniker(self._legacy_session_id(websocket))
        except Exception:
            return None

    def _add_spectator(self, websocket: Any, table_moniker: str) -> None:
        try:
            ws_id = str(websocket.id)
        except Exception:
            ws_id = ""
        sessions = self.sessions
        add_sp = getattr(sessions, "add_spectator", None)
        if callable(add_sp):
            try:
                state = getattr(sessions, "get_by_websocket", lambda _: None)(ws_id)
                if state is not None:
                    add_sp(state.session_id, table_moniker)
                    return
            except Exception:
                pass
        try:
            sessions.add_spectator(table_moniker, self._legacy_session_id(websocket))
        except Exception as e:
            io.echo(f"_add_spectator: {e}", level="warning")

    def _remove_spectator(self, websocket: Any, table_moniker: str) -> None:
        try:
            ws_id = str(websocket.id)
        except Exception:
            ws_id = ""
        sessions = self.sessions
        rm_sp = getattr(sessions, "remove_spectator", None)
        if callable(rm_sp):
            try:
                state = getattr(sessions, "get_by_websocket", lambda _: None)(ws_id)
                if state is not None:
                    rm_sp(state.session_id, table_moniker)
                    return
            except Exception:
                pass
        try:
            sessions.remove_spectator(table_moniker, self._legacy_session_id(websocket))
        except Exception as e:
            io.echo(f"_remove_spectator: {e}", level="warning")


class GameServiceHandler(BaseService):
    """Handle game messages."""

    from casino.services.game import GameService

    def __init__(
        self,
        args: Any,
        session_manager: Any,
        *,
        secret: Optional[bytes] = None,
        token_store: Any = None,
        instance_id: Optional[str] = None,
        clock: Any = None,
    ) -> None:
        super().__init__(
            args,
            session_manager,
            secret=secret,
            token_store=token_store,
            instance_id=instance_id,
            clock=clock,
        )
        self.game_service = self.GameService(args)

    async def handle_message(
        self, server: Any, websocket: Any, path: str, message: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        msg_type = message.get("type")

        if msg_type in ("hit", "stand", "double", "split", "surrender"):
            return await self._handle_game_action(websocket, msg_type, message, server)

        return None

    def _legacy_session_id(self, websocket: Any) -> int:
        bbs_id = getattr(websocket, "_bbsengine6_session_id", None)
        if bbs_id is not None:
            try:
                return int(bbs_id)
            except (TypeError, ValueError):
                pass
        try:
            return int(websocket.id)
        except Exception:
            return id(websocket)

    async def _handle_game_action(
        self,
        websocket: Any,
        action: str,
        message: Optional[dict[str, Any]] = None,
        server: Optional[Any] = None,
    ) -> Optional[dict[str, Any]]:
        if action == "bet":
            return {
                "type": "error",
                "code": "invalid_request",
                "message": "Use bet message with amount",
            }

        state, err = self._check_access(websocket, action, message or {})
        if err is not None:
            return err

        moniker = state.moniker
        session_id = self._legacy_session_id(websocket)
        # Reuse the seated-table lookup from TableServiceHandler via duck typing.
        table_moniker = getattr(state, "table_moniker", None)
        io.echo(
            f"_handle_game_action: action={action}, session_id={session_id}, table_moniker={table_moniker}",
            level="info",
        )
        if not table_moniker:
            return {"type": "error", "code": "not_at_table"}

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
            observer_count = len(self._get_observers(table_moniker))
            player_count = self._get_player_count(table_moniker)
            io.echo(
                f"broadcast game_state: channel=casino:table:{table_moniker} "
                f"phase={broadcast_state.get('phase', '?')} "
                f"players={player_count} observers={observer_count}",
                level="info",
            )
            await server.publish(f"casino:table:{table_moniker}", broadcast_state)

        return game_state

    def _get_observers(self, table_moniker: str) -> set:
        sessions = self.sessions
        getter = getattr(sessions, "get_table_observers", None)
        if callable(getter):
            try:
                return getter(table_moniker)
            except Exception:
                return set()
        return set()

    def _get_player_count(self, table_moniker: str) -> int:
        sessions = self.sessions
        getter = getattr(sessions, "get_table_player_count", None)
        if callable(getter):
            try:
                return int(getter(table_moniker))
            except Exception:
                return 0
        return 0


class BetServiceHandler(BaseService):
    """Handle bet messages."""

    from casino.services.game import GameService

    def __init__(
        self,
        args: Any,
        session_manager: Any,
        *,
        secret: Optional[bytes] = None,
        token_store: Any = None,
        instance_id: Optional[str] = None,
        clock: Any = None,
    ) -> None:
        super().__init__(
            args,
            session_manager,
            secret=secret,
            token_store=token_store,
            instance_id=instance_id,
            clock=clock,
        )
        self.game_service = self.GameService(args)

    async def handle_message(
        self, server: Any, websocket: Any, path: str, message: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        msg_type = message.get("type")

        if msg_type == "bet":
            return await self._handle_bet(websocket, message, server)

        return None

    def _legacy_session_id(self, websocket: Any) -> int:
        bbs_id = getattr(websocket, "_bbsengine6_session_id", None)
        if bbs_id is not None:
            try:
                return int(bbs_id)
            except (TypeError, ValueError):
                pass
        try:
            return int(websocket.id)
        except Exception:
            return id(websocket)

    async def _handle_bet(
        self,
        websocket: Any,
        message: dict[str, Any],
        server: Optional[Any] = None,
    ) -> Optional[dict[str, Any]]:
        state, err = self._check_access(websocket, "bet", message)
        if err is not None:
            return err

        moniker = state.moniker
        session_id = self._legacy_session_id(websocket)
        table_moniker = getattr(state, "table_moniker", None) or message.get("table_moniker")
        io.echo(
            f"_handle_bet: session_id={session_id}, moniker={moniker}, table_moniker={table_moniker}",
            level="info",
        )
        if not table_moniker:
            return {"type": "error", "code": "not_at_table"}

        amount = message.get("amount", 0)

        if not isinstance(amount, int) or amount <= 0:
            io.echo(
                f"_handle_bet: WARNING: Invalid bet attempt from {moniker} at {table_moniker}: "
                f"amount={amount!r} (type={type(amount).__name__})",
                level="warning",
            )
            return {
                "type": "error",
                "code": "invalid_bet",
                "message": "Bet amount must be a positive integer",
            }

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
                observer_count = len(self._get_observers(table_moniker))
                player_count = self._get_player_count(table_moniker)
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
            io.echo(f"_handle_bet: FAILED: {moniker} bet {amount} at {table_moniker}: {error_msg}", level="warning")
            return {"type": "error", "code": "bet_failed", "message": error_msg}

    def _get_observers(self, table_moniker: str) -> set:
        sessions = self.sessions
        getter = getattr(sessions, "get_table_observers", None)
        if callable(getter):
            try:
                return getter(table_moniker)
            except Exception:
                return set()
        return set()

    def _get_player_count(self, table_moniker: str) -> int:
        sessions = self.sessions
        getter = getattr(sessions, "get_table_player_count", None)
        if callable(getter):
            try:
                return int(getter(table_moniker))
            except Exception:
                return 0
        return 0


class ChatServiceHandler(BaseService):
    """Handle chat messages."""

    def __init__(
        self,
        args: Any,
        session_manager: Any,
        *,
        secret: Optional[bytes] = None,
        token_store: Any = None,
        instance_id: Optional[str] = None,
        clock: Any = None,
    ) -> None:
        super().__init__(
            args,
            session_manager,
            secret=secret,
            token_store=token_store,
            instance_id=instance_id,
            clock=clock,
        )

    async def handle_message(
        self, server: Any, websocket: Any, path: str, message: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        msg_type = message.get("type")

        if msg_type in ("chat_table", "chat_global", "emote"):
            return await self._handle_chat(websocket, msg_type, message)

        return None

    async def _handle_chat(
        self,
        websocket: Any,
        msg_type: str,
        message: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        op = msg_type  # chat_table / chat_global / emote map directly to op
        state, err = self._check_access(websocket, op, message)
        if err is not None:
            return err

        moniker = state.moniker
        chat_msg = message.get("message", "")
        table_moniker = getattr(state, "table_moniker", None)

        if msg_type == "chat_table":
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
            return {
                "type": "chat_message",
                "from_moniker": moniker,
                "message": chat_msg,
                "scope": "table" if table_moniker else "global",
                "moniker": table_moniker,
                "timestamp": datetime.utcnow().isoformat(),
            }

        return None

        return None


class SlotServiceHandler(BaseService):
    """Handle slot machine messages.

    Message types:
    - ``slot_spin``         - client request: spin the reels
    - ``slot_paytable``     - client request: get the table's paytable
    - ``slot_history``      - client request: get the player's recent spins
    - ``slot_table_history`` - client request: get the table's recent spins
    """

    def __init__(
        self,
        args: Any,
        session_manager: Any,
        channel_state: Optional[ChannelState] = None,
        *,
        secret: Optional[bytes] = None,
        token_store: Any = None,
        instance_id: Optional[str] = None,
        clock: Any = None,
    ) -> None:
        super().__init__(
            args,
            session_manager,
            secret=secret,
            token_store=token_store,
            instance_id=instance_id,
            clock=clock,
        )
        self.channel_state = channel_state
        from casino.services.slots import (
            handle_get_history as _handle_history,
        )
        from casino.services.slots import (
            handle_get_paytable as _handle_paytable,
        )
        from casino.services.slots import (
            handle_get_table_history as _handle_table_history,
        )
        from casino.services.slots import (
            handle_spin as _handle_spin,
        )

        self._handle_spin = _handle_spin
        self._handle_paytable = _handle_paytable
        self._handle_history = _handle_history
        self._handle_table_history = _handle_table_history

    async def handle_message(
        self, server: Any, websocket: Any, path: str, message: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        msg_type = message.get("type")
        if msg_type == "slot_spin":
            return await self._handle_spin_msg(websocket, message, server)
        if msg_type == "slot_paytable":
            return await self._handle_paytable_msg(websocket, message)
        if msg_type == "slot_history":
            return await self._handle_history_msg(websocket, message)
        if msg_type == "slot_table_history":
            return await self._handle_table_history_msg(websocket, message)
        return None

    def _legacy_session_id(self, websocket: Any) -> int:
        # Prefer the server-assigned ``_bbsengine6_session_id`` if
        # present; the auth flow uses the same id when registering the
        # session. Falls back to ``int(websocket.id)`` (legacy
        # websockets library attribute) and finally to ``id(ws)`` so
        # older test doubles that don't expose either still work.
        bbs_id = getattr(websocket, "_bbsengine6_session_id", None)
        if bbs_id is not None:
            try:
                return int(bbs_id)
            except (TypeError, ValueError):
                pass
        try:
            return int(websocket.id)
        except Exception:
            return id(websocket)

    def _get_seated(self, websocket: Any) -> Optional[str]:
        bbs_id = getattr(websocket, "_bbsengine6_session_id", None)
        sessions = self.sessions
        if bbs_id is not None:
            get_by_websocket = getattr(sessions, "get_by_websocket", None)
            if callable(get_by_websocket):
                try:
                    state = get_by_websocket(str(bbs_id))
                    if state is not None:
                        return state.table_moniker
                except Exception:
                    pass
        try:
            ws_id = str(websocket.id)
        except Exception:
            ws_id = ""
        get_by_websocket = getattr(sessions, "get_by_websocket", None)
        if callable(get_by_websocket):
            try:
                state = get_by_websocket(ws_id)
                if state is not None:
                    return state.table_moniker
            except Exception:
                pass
        try:
            return sessions.get_table_moniker(self._legacy_session_id(websocket))
        except Exception:
            return None

    async def _handle_spin_msg(
        self,
        websocket: Any,
        message: dict[str, Any],
        server: Optional[Any] = None,
    ) -> dict[str, Any]:
        state, err = self._check_access(websocket, "slot_spin", message)
        if err is not None:
            return err

        bet = message.get("bet", 0)
        table_moniker = message.get("table_moniker") or self._get_seated(websocket)
        message["table_moniker"] = table_moniker
        if not table_moniker:
            return {"type": "error", "code": "not_at_table"}

        result = self._handle_spin(self.args, table_moniker, state.moniker, bet)

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
                "player_moniker": state.moniker,
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
        websocket: Any,
        message: dict[str, Any],
    ) -> dict[str, Any]:
        state, err = self._check_access(websocket, "slot_paytable", message)
        if err is not None:
            return err

        table_moniker = message.get("table_moniker") or self._get_seated(websocket)
        message["table_moniker"] = table_moniker
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
        websocket: Any,
        message: dict[str, Any],
    ) -> dict[str, Any]:
        # Resolve session first so we can seed ``message["moniker"]``
        # before the access policy reads it.
        from casino.api._auth import _get_or_bind_session_for

        state, err = _get_or_bind_session_for(self, websocket, message)
        if err is not None:
            return err
        if state is not None:
            message["moniker"] = state.moniker
        state, err = self._check_access(websocket, "slot_history", message)
        if err is not None:
            return err

        try:
            limit = int(message.get("limit", 50))
        except (TypeError, ValueError):
            return {"type": "error", "code": "invalid_request", "message": "limit must be an integer"}
        if limit < 0:
            return {"type": "error", "code": "invalid_request", "message": "limit must be non-negative"}
        history = self._handle_history(self.args, state.moniker, limit)
        return {"type": "slot_history", "spins": history}

    async def _handle_table_history_msg(
        self,
        websocket: Any,
        message: dict[str, Any],
    ) -> dict[str, Any]:
        # Resolve session first so we can seed ``message["table_moniker"]``
        # from the session's bound table before the access policy reads it.
        from casino.api._auth import _get_or_bind_session_for

        state, err = _get_or_bind_session_for(self, websocket, message)
        if err is not None:
            return err
        if state is not None and not message.get("table_moniker"):
            message["table_moniker"] = self._get_seated(websocket)
        state, err = self._check_access(websocket, "slot_table_history", message)
        if err is not None:
            return err

        table_moniker = message.get("table_moniker") or self._get_seated(websocket)
        if not table_moniker:
            return {"type": "error", "code": "not_at_table"}
        try:
            limit = int(message.get("limit", 50))
        except (TypeError, ValueError):
            return {"type": "error", "code": "invalid_request", "message": "limit must be an integer"}
        if limit < 0:
            return {"type": "error", "code": "invalid_request", "message": "limit must be non-negative"}
        history = self._handle_table_history(self.args, table_moniker, limit=limit)
        return {
            "type": "slot_table_history",
            "table_moniker": table_moniker,
            "spins": history,
        }


class MessageRouter:
    """
    Main message handler that coordinates all services.
    Handles broadcasting and session lifecycle.

    Optional ``session_registry``, ``secret``, ``token_store``, and
    ``instance_id`` kwargs mirror ``bed.api.bank.BankService`` wiring:
    when BED loads the router it forwards its
    :class:`SessionRegistry` so handlers can look up the
    cryptographically-bound session the auth flow registered. The
    token-wiring trio enables the per-call defense-in-depth check in
    ``casino.api._auth.check_access``. When the wiring is absent the
    handlers fall back to the standalone CasinoSessionManager + the
    in-memory auth shim (door-mode / legacy tests).
    """

    def __init__(
        self,
        args: Any,
        channel_state: Optional[ChannelState] = None,
        server: Any = None,
        *,
        session_registry: Any = None,
        secret: Optional[bytes] = None,
        token_store: Any = None,
        instance_id: Optional[str] = None,
        clock: Any = None,
    ):
        self.args = args
        self.session_registry = session_registry
        self.sessions = session_registry if session_registry is not None else CasinoSessionManager()

        # Channel subscription state for pub/sub messaging. Accept a
        # shared state from the caller (typically BED) so that
        # server.publish(...) and ChannelServiceHandler see the same
        # subscriptions. Falls back to a private state when no shared
        # state is provided (legacy/standalone use).
        self.channel_state = channel_state if channel_state is not None else ChannelState()
        self.server = server

        # Forward token wiring to every handler so the per-call
        # defense-in-depth check sees a consistent snapshot.
        token_kwargs = dict(
            secret=secret,
            token_store=token_store,
            instance_id=instance_id,
            clock=clock,
        )

        # Create services
        self.auth_service = AuthService(args, self.sessions, self.channel_state)
        self.table_service = TableServiceHandler(
            args, self.sessions, self.channel_state, **token_kwargs
        )
        self.game_service = GameServiceHandler(args, self.sessions, **token_kwargs)
        self.bet_service = BetServiceHandler(args, self.sessions, **token_kwargs)
        self.chat_service = ChatServiceHandler(args, self.sessions, **token_kwargs)
        self.slot_service = SlotServiceHandler(
            args, self.sessions, self.channel_state, **token_kwargs
        )
        self.yahtzee_service_handler = YahtzeeServiceHandler(
            args, self.sessions, **token_kwargs
        )
        self.tictactoe_service_handler = TictactoeServiceHandler(
            args, self.sessions, **token_kwargs
        )

    def register_all(self, server: Any) -> None:
        """Register all services with the WebSocketServer.

        ``auth`` is owned by ``bed.api.auth.AuthService`` (registered
        by ``bed.main.BED.start`` before any router loads). When that
        service is already on the server we skip our ``auth`` /
        ``ping`` registration entirely so the casino envelope shape
        (which drops ``token`` / ``session_id`` / ``expires_at``)
        never shadows bed's.

        When the router is loaded standalone (the in-process tests
        in ``casino.tests.test_server`` spin up a bare
        ``WebSocketServer`` with no bed in front of it) no auth
        service is registered yet, so we fall back to casino's own
        ``AuthService`` for ``auth`` and ``ping`` to keep those
        tests green. ``self.auth_service`` and the
        ``casino.api.handler.AuthService`` class itself are still
        defined unconditionally so any other code path that imports
        them continues to work.
        """
        if server.get_service("auth") is None:
            server.register_service(self.auth_service, ["auth", "ping"])
        server.register_service(
            self.table_service,
            [
                "list_tables",
                "create_table",
                "update_table",
                "join_table",
                "leave_table",
                "watch_table",
                "stop_watching",
            ],
        )
        server.register_service(self.game_service, ["hit", "stand", "double", "split", "surrender"])
        server.register_service(self.bet_service, ["bet"])
        server.register_service(self.chat_service, ["chat_table", "chat_global", "emote"])

        # Register slot service for slot machine play
        server.register_service(self.slot_service, ["slot_spin", "slot_paytable", "slot_history", "slot_table_history"])

        # Register yahtzee service for dice play
        server.register_service(
            self.yahtzee_service_handler, ["yahtzee_quick_play", "yahtzee_roll", "yahtzee_reroll", "yahtzee_score"]
        )

        # Register tictactoe service for board play
        server.register_service(
            self.tictactoe_service_handler,
            ["tictactoe_quick_play", "tictactoe_move", "tictactoe_resign", "tictactoe_join"],
        )

    async def handle_broadcast(self, server: Any, websocket: Any, path: str, message: dict[str, Any]) -> None:
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
            self.tictactoe_service_handler.finalize_on_disconnect(table_moniker, leaving_moniker)
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
        self, server: Any, websocket: Any, path: str, message: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
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
