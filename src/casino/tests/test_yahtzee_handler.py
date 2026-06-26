# casino/tests/test_yahtzee_handler.py
# Tests for yahtzee/api_handler.py: BED message dispatch, auth,
# routing, broadcast, disconnect cleanup.

import asyncio
import random
from unittest.mock import AsyncMock, MagicMock, patch

from casino.yahtzee.api_handler import YahtzeeServiceHandler
from casino.yahtzee.dealer import YahtzeeDealer
from casino.yahtzee.service import YahtzeeService


def _make_args():
    return MagicMock()


def _make_service():
    """YahtzeeService with all DB-touching deps mocked out."""
    ts = MagicMock()
    ts.create_table.return_value = {
        "success": True,
        "table": {
            "moniker": "yahtzee-alice", "type": "yahtzee",
            "minimumbet": 10, "maximumbet": 1000,
            "ownermoniker": "alice", "status": "open",
            "hidden": True, "accountid": 1,
        },
        "message": "ok",
    }
    dealer = YahtzeeDealer(rng=random.Random(0))
    return YahtzeeService(
        _make_args(), dealer=dealer, table_service=ts,
        find_table_fn=MagicMock(return_value=None),
    )


def _make_handler():
    sessions = MagicMock()
    service = _make_service()
    handler = YahtzeeServiceHandler(_make_args(), sessions, service=service)
    return handler, sessions, service


def _mock_db():
    """Patch dal_bet, dal_game, database. Returns the mocks."""
    db = MagicMock()
    dg = MagicMock()
    dbconn = MagicMock()
    dg.create_game.return_value = {"id": 42}
    db.place_bet.return_value = {"id": 7}
    return db, dg, dbconn


class _DBSession:
    """Context manager that patches dal_bet, dal_game, database for
    the duration of a with block. Yields (db, dg, dbconn) mocks."""

    def __enter__(self):
        self.db = MagicMock()
        self.dg = MagicMock()
        self.dbconn = MagicMock()
        self.dg.create_game.return_value = {"id": 42}
        self.db.place_bet.return_value = {"id": 7}
        self._p1 = patch("casino.yahtzee.service.dal_bet", self.db)
        self._p2 = patch("casino.yahtzee.service.dal_game", self.dg)
        self._p3 = patch("casino.yahtzee.service.database", self.dbconn)
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
    def test_quick_play_returns_state(self):
        handler, sessions, service = _make_handler()
        sessions.get_moniker.return_value = "alice"
        server = MagicMock()
        server.publish = AsyncMock()
        with _DBSession():
            result = asyncio.run(handler.handle_message(
                server, MagicMock(), "/", {"type": "yahtzee_quick_play"},
            ))
        assert result["round"] == 0
        sessions.set_table_moniker.assert_called()

    def test_unknown_msg_type_returns_none(self):
        handler, sessions, _ = _make_handler()
        result = asyncio.run(handler.handle_message(
            MagicMock(), MagicMock(), "/", {"type": "yahtzee_bogus"},
        ))
        assert result is None

    def test_roll_requires_session_table(self):
        handler, sessions, _ = _make_handler()
        sessions.get_moniker.return_value = "alice"
        sessions.get_table_moniker.return_value = None
        result = asyncio.run(handler.handle_message(
            MagicMock(), MagicMock(), "/", {"type": "yahtzee_roll"},
        ))
        assert result["type"] == "error"
        assert result["code"] == "not_at_table"

    def test_score_after_quick_play(self):
        handler, sessions, service = _make_handler()
        sessions.get_moniker.return_value = "alice"
        server = MagicMock()
        server.publish = AsyncMock()
        with _DBSession():
            asyncio.run(handler.handle_message(
                server, MagicMock(), "/", {"type": "yahtzee_quick_play"},
            ))
            sessions.get_table_moniker.return_value = "yahtzee-alice"
            result_roll = asyncio.run(handler.handle_message(
                server, MagicMock(), "/", {"type": "yahtzee_roll"},
            ))
            assert result_roll["rolls_left"] == 1
            result_score = asyncio.run(handler.handle_message(
                server, MagicMock(), "/",
                {"type": "yahtzee_score", "category": "chance"},
            ))
        assert result_score["type"] == "yahtzee_state"
        assert result_score["round"] == 1

    def test_bad_category_returns_error(self):
        handler, sessions, service = _make_handler()
        sessions.get_moniker.return_value = "alice"
        sessions.get_table_moniker.return_value = "yahtzee-alice"
        server = MagicMock()
        server.publish = AsyncMock()
        with _DBSession():
            service.quick_play("alice")
            service.roll("yahtzee-alice", "alice")
            result = asyncio.run(handler.handle_message(
                server, MagicMock(), "/",
                {"type": "yahtzee_score", "category": "bogus"},
            ))
        assert result["type"] == "error"
        assert result["code"] == "bad_category"


class TestAuth:
    def test_unauthenticated_session_rejected(self):
        handler, sessions, _ = _make_handler()
        sessions.get_moniker.return_value = None
        result = asyncio.run(handler.handle_message(
            MagicMock(), MagicMock(), "/", {"type": "yahtzee_quick_play"},
        ))
        assert result["type"] == "error"
        assert result["code"] == "not_authenticated"


class TestBroadcast:
    def test_publishes_to_table_channel(self):
        handler, sessions, _ = _make_handler()
        sessions.get_moniker.return_value = "alice"
        server = MagicMock()
        server.publish = AsyncMock()
        with _DBSession():
            asyncio.run(handler.handle_message(
                server, MagicMock(), "/", {"type": "yahtzee_quick_play"},
            ))
        assert server.publish.await_count == 1
        call = server.publish.await_args
        assert call.args[0] == "casino:table:yahtzee-alice"
        assert call.args[1]["type"] == "yahtzee_state"

    def test_publish_failure_is_swallowed(self):
        handler, sessions, _ = _make_handler()
        sessions.get_moniker.return_value = "alice"
        server = MagicMock()
        async def bad_publish(*a, **kw):
            raise RuntimeError("nope")
        server.publish = bad_publish
        with _DBSession():
            result = asyncio.run(handler.handle_message(
                server, MagicMock(), "/", {"type": "yahtzee_quick_play"},
            ))
        assert result["round"] == 0


class TestFinalizeOnDisconnect:
    def test_delegates_to_service(self):
        handler, _, service = _make_handler()
        with _DBSession():
            service.quick_play("alice")
            result = handler.finalize_on_disconnect("yahtzee-alice")
        assert result is True
        assert service.get_game("yahtzee-alice") is None

    def test_returns_false_when_no_game(self):
        handler, _, service = _make_handler()
        assert handler.finalize_on_disconnect("nonexistent") is False
