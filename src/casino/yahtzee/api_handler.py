# casino/yahtzee/api_handler.py
# BED message dispatch for yahtzee. Mirrors SlotServiceHandler pattern.
#
# Message types:
# - ``yahtzee_quick_play`` - lazy-create table + start a session
# - ``yahtzee_roll``         - server rolls 5 dice, decrements rolls_left
# - ``yahtzee_reroll``       - server rolls unlocked dice, decrements rolls_left
# - ``yahtzee_score``        - score current dice into a category, advance round
#
# The handler does NOT itself do money or DB work; that lives in
# ``YahtzeeService``. The handler is a thin dispatch layer that
# authenticates the session, resolves the table_moniker, and
# publishes state changes to the table channel so spectators see
# dice.

from __future__ import annotations

from typing import Any, Optional

from bbsengine6 import io

from casino.api._auth import check_access as _check_access_pipeline

from .service import YahtzeeService


class YahtzeeServiceHandler:
    """BED message dispatch for yahtzee.

    Note: this class is *not* a ``BaseService`` subclass because the
    YahtzeeService is constructed per-table, not per-BED, and the
    service does not need a websocket for the work it does (it
    reads/writes the DB synchronously). The handler is a thin
    async wrapper that authenticates, dispatches, and broadcasts.

    Despite the name, the API surface matches ``BaseService``:
    ``__init__(args, sessions)`` and ``async handle_message(server,
    websocket, path, message)``. The MessageRouter
    ``register_all`` calls ``register_service(handler, msg_types)``
    with the same call shape.

    The handler carries the same optional token wiring as
    ``casino.api.handler.BaseService`` so the per-op
    :func:`casino.access` decision is enforced through
    the shared five-gate pipeline. When the wiring is absent
    (door-mode / legacy tests) the token gates become no-ops and
    authorization falls back to session-based lookup.
    """

    YAHTZEE_MSG_TYPES = (
        "yahtzee_quick_play",
        "yahtzee_roll",
        "yahtzee_reroll",
        "yahtzee_score",
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
        service: YahtzeeService | None = None,
        *,
        secret: Optional[bytes] = None,
        token_store: Any = None,
        instance_id: Optional[str] = None,
        clock: Any = None,
        pool: Any = None,
    ) -> None:
        self.args = args
        self.sessions = sessions
        self._service = (
            service if service is not None else YahtzeeService(args, pool=pool)
        )
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
    def yahtzee_service(self) -> YahtzeeService:
        return self._service

    async def handle_message(
        self,
        server: Any,
        websocket: Any,
        path: str,
        message: dict,
    ) -> dict | None:
        msg_type = message.get("type")
        if msg_type not in self.YAHTZEE_MSG_TYPES:
            return None

        state, err = self._check_access(websocket, msg_type, message)
        if err is not None:
            return err

        moniker = state.moniker
        legacy_session_id = self._legacy_session_id(websocket)

        if msg_type == "yahtzee_quick_play":
            result = self._service.quick_play(moniker)
            table_moniker = result.get("table_moniker")
            if table_moniker:
                self._set_seated(websocket, table_moniker)
            result = dict(result)
            result["type"] = "yahtzee_state"
            await self._broadcast(server, result)
            return result

        # All other actions require the player to be at a table
        table_moniker = getattr(state, "table_moniker", None)
        if not table_moniker:
            return {"type": "error", "code": "not_at_table"}

        try:
            if msg_type == "yahtzee_roll":
                result = self._service.roll(table_moniker, moniker)
                if isinstance(result, dict) and "type" not in result:
                    result = dict(result)
                    result["type"] = "yahtzee_state"
            elif msg_type == "yahtzee_reroll":
                locks = list(message.get("locks") or [])
                if not all(isinstance(i, int) for i in locks):
                    return {"type": "error", "code": "bad_locks",
                            "message": "locks must be a list of integers"}
                result = self._service.reroll(table_moniker, moniker, locks)
                if isinstance(result, dict) and "type" not in result:
                    result = dict(result)
                    result["type"] = "yahtzee_state"
            elif msg_type == "yahtzee_score":
                category = message.get("category", "")
                if not isinstance(category, str):
                    return {"type": "error", "code": "bad_category",
                            "message": "category must be a string"}
                result = self._service.score(table_moniker, moniker, category)
            else:
                return None
        except KeyError as e:
            return {"type": "error", "code": "no_active_game", "message": str(e)}
        except PermissionError as e:
            return {"type": "error", "code": "wrong_player", "message": str(e)}

        # Broadcast state (or result) to spectators
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
            io.echo(f"yahtzee broadcast failed: {e}", level="warning")

    def finalize_on_disconnect(self, table_moniker: str) -> bool:
        """Hook called by MessageRouter.unregister_session when a
        player disconnects mid-game."""
        return self._service.finalize_on_disconnect(table_moniker)

    def _legacy_session_id(self, websocket: Any) -> int:
        try:
            return int(websocket.id)
        except Exception:
            return id(websocket)

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
            sessions.set_table_moniker(self._legacy_session_id(websocket), table_moniker)
        except Exception:
            pass
