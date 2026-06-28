# casino/tests/test_tictactoe_handler.py
# Tests for tictactoe/api_handler.py: BED message dispatch, auth,
# routing, broadcast, mode-0 streaming, disconnect cleanup.

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from casino.tictactoe.api_handler import TictactoeServiceHandler
from casino.tictactoe.dealer import TictactoeDealer
from casino.tictactoe.service import TictactoeService


def _make_args():
    return MagicMock()


def _make_service():
    """TictactoeService with all DB-touching deps mocked out."""
    ts = MagicMock()
    ts.create_table.return_value = {
        "success": True,
        "table": {
            "moniker": "ttt-alice", "type": "tictactoe",
            "minimumbet": 10, "maximumbet": 1000,
            "ownermoniker": "alice", "status": "open",
            "hidden": True, "accountid": 1,
        },
        "message": "ok",
    }
    dealer = TictactoeDealer()
    return TictactoeService(
        _make_args(), dealer=dealer, table_service=ts,
        find_table_fn=MagicMock(return_value=None),
    )


def _make_handler():
    sessions = MagicMock()
    service = _make_service()
    handler = TictactoeServiceHandler(_make_args(), sessions, service=service)
    return handler, sessions, service


class _DBSession:
    """Context manager that patches dal_bet, dal_game, database for
    the duration of a with block."""

    def __enter__(self):
        self.db = MagicMock()
        self.dg = MagicMock()
        self.dbconn = MagicMock()
        self.dg.create_game.return_value = {"id": 42}
        self.db.place_bet.return_value = {"id": 7}
        self._p1 = patch("casino.tictactoe.service.dal_bet", self.db)
        self._p2 = patch("casino.tictactoe.service.dal_game", self.dg)
        self._p3 = patch("casino.tictactoe.service.database", self.dbconn)
        self._p1.start()
        self._p2.start()
        self._p3.start()
        return self

    def __exit__(self, *a):
        self._p1.stop()
        self._p2.stop()
        self._p3.stop()
        return False


class TestDispatch:
    def test_quick_play_mode_1_returns_state(self):
        handler, sessions, _ = _make_handler()
        sessions.get_moniker.return_value = "alice"
        server = MagicMock()
        server.publish = AsyncMock()
        with _DBSession():
            result = asyncio.run(handler.handle_message(
                server, MagicMock(), "/",
                {"type": "tictactoe_quick_play", "mode": 1},
            ))
        assert result["type"] == "tictactoe_state"
        assert result["mode"] == 1
        assert result["moves_played"] == 0
        sessions.set_table_moniker.assert_called()

    def test_quick_play_bad_mode_rejected(self):
        handler, sessions, _ = _make_handler()
        sessions.get_moniker.return_value = "alice"
        server = MagicMock()
        server.publish = AsyncMock()
        result = asyncio.run(handler.handle_message(
            server, MagicMock(), "/",
            {"type": "tictactoe_quick_play", "mode": "one"},
        ))
        assert result["type"] == "error"
        assert result["code"] == "bad_mode"

    def test_unknown_msg_type_returns_none(self):
        handler, sessions, _ = _make_handler()
        result = asyncio.run(handler.handle_message(
            MagicMock(), MagicMock(), "/", {"type": "tictactoe_bogus"},
        ))
        assert result is None

    def test_move_requires_session_table(self):
        handler, sessions, _ = _make_handler()
        sessions.get_moniker.return_value = "alice"
        sessions.get_table_moniker.return_value = None
        result = asyncio.run(handler.handle_message(
            MagicMock(), MagicMock(), "/",
            {"type": "tictactoe_move", "cell": 0},
        ))
        assert result["type"] == "error"
        assert result["code"] == "not_at_table"

    def test_move_after_quick_play(self):
        handler, sessions, _ = _make_handler()
        sessions.get_moniker.return_value = "alice"
        server = MagicMock()
        server.publish = AsyncMock()
        with _DBSession():
            asyncio.run(handler.handle_message(
                server, MagicMock(), "/",
                {"type": "tictactoe_quick_play", "mode": 1},
            ))
            sessions.get_table_moniker.return_value = "ttt-alice"
            result = asyncio.run(handler.handle_message(
                server, MagicMock(), "/",
                {"type": "tictactoe_move", "cell": 4},
            ))
        assert result["type"] == "tictactoe_state"
        assert result["moves_played"] == 2  # alice + AI

    def test_move_non_int_cell_rejected(self):
        handler, sessions, _ = _make_handler()
        sessions.get_moniker.return_value = "alice"
        sessions.get_table_moniker.return_value = "ttt-alice"
        result = asyncio.run(handler.handle_message(
            MagicMock(), MagicMock(), "/",
            {"type": "tictactoe_move", "cell": "0"},
        ))
        assert result["type"] == "error"
        assert result["code"] == "cell_out_of_range"


class TestAuth:
    def test_unauthenticated_session_rejected(self):
        handler, sessions, _ = _make_handler()
        sessions.get_moniker.return_value = None
        result = asyncio.run(handler.handle_message(
            MagicMock(), MagicMock(), "/",
            {"type": "tictactoe_quick_play", "mode": 1},
        ))
        assert result["type"] == "error"
        assert result["code"] == "not_authenticated"


class TestMode0Streaming:
    def test_mode0_streams_self_play(self):
        handler, sessions, _ = _make_handler()
        sessions.get_moniker.return_value = "alice"
        server = MagicMock()
        server.publish = AsyncMock()
        with _DBSession():
            asyncio.run(handler.handle_message(
                server, MagicMock(), "/",
                {"type": "tictactoe_quick_play", "mode": 0},
            ))
        # Many publishes: the initial state + per-move states + the result
        publishes = server.publish.await_args_list
        # At minimum: initial state + last (result). Could be 6+ states.
        assert len(publishes) >= 5
        # Final payload is a tictactoe_result
        last = publishes[-1]
        assert last.args[1]["type"] == "tictactoe_result"
        # Perfect vs perfect -> draw
        assert last.args[1]["winner"] == 0


class TestBroadcast:
    def test_publishes_to_table_channel(self):
        handler, sessions, _ = _make_handler()
        sessions.get_moniker.return_value = "alice"
        server = MagicMock()
        server.publish = AsyncMock()
        with _DBSession():
            asyncio.run(handler.handle_message(
                server, MagicMock(), "/",
                {"type": "tictactoe_quick_play", "mode": 1},
            ))
        assert server.publish.await_count >= 1
        call = server.publish.await_args
        assert call.args[0] == "casino:table:ttt-alice"
        assert call.args[1]["type"] == "tictactoe_state"

    def test_publish_failure_is_swallowed(self):
        handler, sessions, _ = _make_handler()
        sessions.get_moniker.return_value = "alice"
        server = MagicMock()
        async def bad_publish(*a, **kw):
            raise RuntimeError("nope")
        server.publish = bad_publish
        with _DBSession():
            result = asyncio.run(handler.handle_message(
                server, MagicMock(), "/",
                {"type": "tictactoe_quick_play", "mode": 1},
            ))
        assert result["type"] == "tictactoe_state"


class TestFinalizeOnDisconnect:
    def test_delegates_to_service(self):
        handler, _, service = _make_handler()
        with _DBSession():
            service.quick_play("alice", mode=1)
            result = handler.finalize_on_disconnect("ttt-alice", "alice")
        assert result is True
        assert service.get_game("ttt-alice") is None

    def test_returns_false_when_no_game(self):
        handler, _, _ = _make_handler()
        assert handler.finalize_on_disconnect("nonexistent", "alice") is False
