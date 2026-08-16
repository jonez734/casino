# casino/tictactoe/api_handler.py
# BED message dispatch for tic-tac-toe. Mirrors YahtzeeServiceHandler.
#
# Message types:
# - ``tictactoe_quick_play`` - lazy-create table + start a session
# - ``tictactoe_move``        - human move in modes 1 and 2
# - ``tictactoe_resign``      - forefeit; opponent wins
# - ``tictactoe_join``        - mode 2: second human takes the O seat
#
# The handler is a thin dispatch layer that authenticates the
# session, resolves the table_moniker, and publishes state changes
# to the table channel so spectators see every move.

from __future__ import annotations

from typing import Any, Optional

from bbsengine6 import io

from casino.api._auth import check_access as _check_access_pipeline

from .service import TictactoeService


class TictactoeServiceHandler:
    """BED message dispatch for tic-tac-toe.

    Mirrors ``YahtzeeServiceHandler``. The service does its own
    bank + DB work; the handler authenticates, dispatches, and
    broadcasts.

    Token-aware: the per-op :func:`bbsengine6.casino.access` decision
    is enforced through the shared five-gate pipeline in
    ``casino.api._auth.check_access``. When the optional token
    wiring (``secret`` / ``token_store`` / ``instance_id``) is not
    provided (door-mode / legacy tests) the token gates become
    no-ops and authorization falls back to session-based lookup.
    """

    TICTACTOE_MSG_TYPES = (
        "tictactoe_quick_play",
        "tictactoe_move",
        "tictactoe_resign",
        "tictactoe_join",
    )

    #: When ``True``, :func:`casino.api._auth.check_access` skips the
    #: cryptographically-verified token gate so door-mode fixtures
    #: that drive the service without a real ``secret`` /
    #: ``token_store`` / ``instance_id`` keep working. Production
    #: handlers under BED leave this ``False``; every gameplay op
    #: then requires a valid wire or session-bound token.
    allow_legacy_session_only: bool = False

    def __init__(
        self,
        args: Any,
        sessions: Any,
        service: TictactoeService | None = None,
        *,
        secret: Optional[bytes] = None,
        token_store: Any = None,
        instance_id: Optional[str] = None,
        clock: Any = None,
    ) -> None:
        self.args = args
        self.sessions = sessions
        self._service = service if service is not None else TictactoeService(args)
        self.secret = bytes(secret) if secret else None
        self.token_store = token_store
        self.instance_id = str(instance_id) if instance_id else None
        self._clock = clock

    def _now(self) -> float:
        if self._clock is not None:
            return float(self._clock())
        import time as _time

        return _time.time()

    def _check_access(
        self, websocket: Any, op: str, message: dict
    ) -> tuple[Optional[Any], Optional[dict]]:
        return _check_access_pipeline(self, websocket, op, message)

    @property
    def tictactoe_service(self) -> TictactoeService:
        return self._service

    async def handle_message(
        self,
        server: Any,
        websocket: Any,
        path: str,
        message: dict,
    ) -> dict | None:
        msg_type = message.get("type")
        if msg_type not in self.TICTACTOE_MSG_TYPES:
            return None

        state, err = self._check_access(websocket, msg_type, message)
        if err is not None:
            return err

        moniker = state.moniker

        if msg_type == "tictactoe_quick_play":
            mode = message.get("mode", 1)
            if not isinstance(mode, int) or isinstance(mode, bool):
                return {"type": "error", "code": "bad_mode",
                        "message": "mode must be 0, 1, or 2"}
            result = self._service.quick_play(moniker, mode=mode)
            table_moniker = result.get("table_moniker")
            if table_moniker:
                self._set_seated(websocket, table_moniker)
            await self._broadcast(server, result)
            # Mode 0: kick off self-play and stream the resulting
            # states.
            if mode == 0 and table_moniker:
                states = self._service.auto_play_mode0(table_moniker)
                for state in states:
                    await self._broadcast(server, state)
            return result

        # All other actions require the player to be at a table
        table_moniker = getattr(state, "table_moniker", None)
        if not table_moniker:
            return {"type": "error", "code": "not_at_table"}

        try:
            if msg_type == "tictactoe_move":
                cell = message.get("cell")
                if not isinstance(cell, int) or isinstance(cell, bool):
                    return {"type": "error", "code": "cell_out_of_range",
                            "message": "cell must be an integer in [0, 8]"}
                result = self._service.play_move(table_moniker, moniker, cell)
            elif msg_type == "tictactoe_resign":
                result = self._service.resign(table_moniker, moniker)
            elif msg_type == "tictactoe_join":
                result = self._service.join(table_moniker, moniker)
            else:
                return None
        except Exception as e:
            return {"type": "error", "code": "internal", "message": str(e)}

        if isinstance(result, dict):
            await self._broadcast(server, result)
        return result

    async def _broadcast(self, server: Any, payload: dict) -> None:
        table_moniker = payload.get("table_moniker")
        if not table_moniker or server is None:
            return
        try:
            await server.publish(f"casino:table:{table_moniker}", payload)
        except Exception as e:
            io.echo(f"tictactoe broadcast failed: {e}", level="warning")

    def finalize_on_disconnect(self, table_moniker: str, leaving_moniker: str | None = None) -> bool:
        """Hook called by MessageRouter.unregister_session when a
        player disconnects mid-game."""
        return self._service.finalize_on_disconnect(table_moniker, leaving_moniker)

    def _set_seated(self, websocket: Any, table_moniker: Optional[str]) -> None:
        try:
            ws_id = str(websocket.id)
        except Exception:
            ws_id = ""
        sessions = self.sessions
        set_tm = getattr(sessions, "set_table_moniker", None)
        if callable(set_tm):
            try:
                state = getattr(sessions, "get_by_websocket", lambda _: None)(ws_id)
                if state is not None:
                    set_tm(state.session_id, table_moniker)
                    return
            except Exception:
                pass
        try:
            sessions.set_table_moniker(
                int(websocket.id) if isinstance(websocket.id, int) else id(websocket),
                table_moniker,
            )
        except Exception:
            pass
