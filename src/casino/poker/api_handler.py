# casino/poker/api_handler.py
# BED message dispatch for poker. Mirrors TictactoeServiceHandler.
#
# Message types (the client's ``poker_*`` contract, see commands/poker/lib.py):
# - poker_create_table   variant, betting_structure, small_blind, big_blind
# - poker_join_table     table_moniker, buy_in
# - poker_leave_table    (no fields)
# - poker_start_hand     (no fields)
# - poker_get_state      (no fields)
# - poker_check | poker_call | poker_fold | poker_all_in
# - poker_bet | poker_raise   amount
#
# Identity comes from the authenticated session, never from a moniker in the message. The
# shared PokerService is in-memory and per-process, so every session sees the same tables.

from __future__ import annotations

from typing import Any, Optional

from bbsengine6 import io

from casino.api._auth import check_access as _check_access_pipeline

from ..services.poker import PokerService

_ACTION_TYPES = {
    "poker_check": "check",
    "poker_call": "call",
    "poker_fold": "fold",
    "poker_all_in": "all_in",
    "poker_bet": "bet",
    "poker_raise": "raise",
}

POKER_MSG_TYPES = (
    "poker_create_table",
    "poker_join_table",
    "poker_leave_table",
    "poker_start_hand",
    "poker_get_state",
    *_ACTION_TYPES.keys(),
)


class PokerServiceHandler:
    """BED message dispatch for poker over the shared in-memory PokerService."""

    POKER_MSG_TYPES = POKER_MSG_TYPES

    #: Production handlers leave this False so every op needs a verified token.
    allow_legacy_session_only: bool = False

    def __init__(
        self,
        args: Any,
        sessions: Any,
        service: Optional[PokerService] = None,
        *,
        secret: Optional[bytes] = None,
        token_store: Any = None,
        instance_id: Optional[str] = None,
        clock: Any = None,
        pool: Any = None,
        channel_state: Any = None,
    ) -> None:
        self.args = args
        self.sessions = sessions
        self.channel_state = channel_state
        self._service = service if service is not None else PokerService(args)
        self.secret = bytes(secret) if secret else None
        self.token_store = token_store
        self.instance_id = str(instance_id) if instance_id else None
        self._clock = clock

    @property
    def poker_service(self) -> PokerService:
        return self._service

    def list_tables(self) -> list[dict]:
        """Lobby entries for in-memory poker tables, shaped like casino.__table rows."""
        return [
            {
                "moniker": t["moniker"],
                "type": "poker",
                "variant": t["variant"],
                "betting_structure": t["betting_structure"],
                "stakes": t["stakes"],
                "players": t["players"],
                "max_players": t["max_players"],
                "game_stage": t["game_stage"],
            }
            for t in self._service.list_tables()
        ]

    def _check_access(self, websocket: Any, op: str, message: dict):
        return _check_access_pipeline(self, websocket, op, message)

    async def handle_message(
        self, server: Any, websocket: Any, path: str, message: dict
    ) -> dict | None:
        msg_type = message.get("type")
        if msg_type not in POKER_MSG_TYPES:
            return None

        state, err = self._check_access(websocket, msg_type, message)
        if err is not None:
            return err

        moniker = state.moniker
        svc = self._service

        try:
            if msg_type == "poker_create_table":
                result = svc.create_table(
                    table_moniker=_new_table_moniker(svc),
                    variant_name=message.get("variant", "holdem"),
                    betting_structure=message.get("betting_structure", "no_limit"),
                    small_blind=int(message.get("small_blind", 1)),
                    big_blind=int(message.get("big_blind", 2)),
                )
                if result.get("success"):
                    from casino.services import table_channels as _tc
                    _tc.create_table_channels(self.args, result["table_moniker"], owner=moniker)
                return _envelope("poker_table_created", result)

            if msg_type == "poker_join_table":
                table_moniker = message.get("table_moniker")
                if not table_moniker:
                    return _bad("table_moniker required")
                result = svc.join_table(table_moniker, moniker, int(message.get("buy_in", 100)))
                if result.get("success"):
                    self._set_seated(websocket, table_moniker)
                    self._subscribe_table(websocket, table_moniker)
                    self._sync_announcers(table_moniker, moniker)
                return _envelope("poker_joined_table", result, table_moniker=table_moniker)

            table_moniker = getattr(state, "table_moniker", None) or self._seated_table(websocket)
            if not table_moniker:
                return {"type": "error", "code": "not_at_table"}

            if msg_type == "poker_leave_table":
                result = svc.leave_table(table_moniker, moniker)
                if result.get("success"):
                    self._set_seated(websocket, None)
                    self._unsubscribe_table(websocket, table_moniker)
                    self._sync_announcers(table_moniker, moniker)
                return _envelope("poker_left_table", result, table_moniker=table_moniker)

            if msg_type == "poker_start_hand":
                result = svc.start_hand(table_moniker)
                if result.get("success"):
                    await self._publish_events(server, table_moniker, moniker, svc)
                return _envelope("poker_hand_started", result, table_moniker=table_moniker)

            if msg_type == "poker_get_state":
                state = svc.get_table_state(table_moniker, moniker)
                return {"type": "poker_state", **state, "last_result": svc.last_result(table_moniker)}

            if msg_type in _ACTION_TYPES:
                amount = int(message.get("amount", 0) or 0)
                result = svc.player_action(table_moniker, moniker, _ACTION_TYPES[msg_type], amount)
                envelope = _envelope(
                    "poker_action_result", {**result, "last_result": svc.last_result(table_moniker)},
                    table_moniker=table_moniker,
                )
                if result.get("success"):
                    await self._publish_events(server, table_moniker, moniker, svc)
                return envelope
        except (TypeError, ValueError) as e:
            return _bad(str(e))
        except Exception as e:  # pragma: no cover - surfaced to the client, never swallowed
            io.echo(f"poker handler error on {msg_type}: {e}", level="error")
            return {"type": "error", "code": "internal", "message": str(e)}

        return {"type": "error", "code": "unhandled_type",
                "message": f"poker has no handler for {msg_type!r}"}

    def _seated_table(self, websocket: Any) -> Optional[str]:
        """The table this session is seated at, from the session store (not the wire)."""
        state = self._session_state(websocket)
        return getattr(state, "table_moniker", None) if state is not None else None

    async def _publish_events(self, server: Any, table_moniker: str, actor: str, svc: Any) -> None:
        """Publish the table's new state and last result to its events channel.

        The events channel is announce-only and is published by the server, so the publish runs as
        the table's seated actor for the permission check. A publish failure is logged, never raised:
        the action has already happened and its direct reply must still reach the sender.
        """
        if server is None or self.channel_state is None:
            return
        try:
            from bbsengine6.net import channel_publish

            from casino.services.table_channels import events_channel

            payload = {
                "type": "poker_event",
                "table_moniker": table_moniker,
                "state": svc.get_table_state(table_moniker, actor),
                "last_result": svc.last_result(table_moniker),
            }
            await channel_publish(
                self.channel_state,
                events_channel(table_moniker),
                payload,
                server=server,
                # No sender: game events are published by the server, so the announce-only
                # check (which is for player-originated publishes) does not refuse a seated player.
                args=self.args,
            )
        except Exception as e:
            io.echo(f"poker events publish failed: {e}", level="warning")

    def _sync_announcers(self, table_moniker: str, owner: str) -> None:
        """Keep the events channel's announcers equal to the table's seats (players and bots)."""
        from casino.services import table_channels as _tc
        result = _tc.sync_announcers(self.args, table_moniker, owner=owner)
        if not result.get("success"):
            io.echo(f"poker announcer sync failed for {table_moniker}: {result.get('failed')}", level="warning")

    def _subscribe_table(self, websocket: Any, table_moniker: str) -> None:
        """Subscribe the seated session to the table's events and chat channels."""
        from casino.services import table_channels as _tc
        if self.channel_state is not None:
            _tc.subscribe_seat(self.channel_state, self._session_key(websocket), table_moniker)

    def _unsubscribe_table(self, websocket: Any, table_moniker: str) -> None:
        from casino.services import table_channels as _tc
        if self.channel_state is not None:
            _tc.unsubscribe_table(self.channel_state, self._session_key(websocket), table_moniker)

    def _session_key(self, websocket: Any) -> int:
        """The int key the channel state uses for ``websocket``: the transport's session id, else
        ``id(websocket)``. This is the same convention as the casino table handler."""
        bbs_id = getattr(websocket, "_bbsengine6_session_id", None)
        return int(bbs_id) if bbs_id is not None else id(websocket)

    def _set_seated(self, websocket: Any, table_moniker: Optional[str]) -> None:
        """Mirror the seat into the session store, the same store check_access reads."""
        state = self._session_state(websocket)
        set_tm = getattr(self.sessions, "set_table_moniker", None)
        if state is None or not callable(set_tm):
            return
        try:
            set_tm(getattr(state, "session_id", None), table_moniker)
        except Exception as e:
            io.echo(f"poker: could not record seat: {e}", level="warning")

    def _session_state(self, websocket: Any) -> Any:
        get_by_websocket = getattr(self.sessions, "get_by_websocket", None)
        if not callable(get_by_websocket):
            return None
        bbs_id = getattr(websocket, "_bbsengine6_session_id", None)
        for key in (str(bbs_id) if bbs_id is not None else None, str(getattr(websocket, "id", ""))):
            if not key:
                continue
            try:
                state = get_by_websocket(key)
            except Exception:
                state = None
            if state is not None:
                return state
        return None


def _envelope(msg_type: str, result: dict, *, table_moniker: Optional[str] = None) -> dict:
    out = {"type": msg_type, **result}
    if table_moniker and "table_moniker" not in out:
        out["table_moniker"] = table_moniker
    return out


def _bad(message: str) -> dict:
    return {"type": "error", "code": "invalid_request", "message": message}


def _new_table_moniker(svc: PokerService) -> str:
    """Next free table moniker, ``poker-N``, not already in use."""
    n = len(svc._tables) + 1
    while f"poker-{n}" in svc._tables:
        n += 1
    return f"poker-{n}"
