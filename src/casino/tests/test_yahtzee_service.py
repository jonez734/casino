# casino/tests/test_yahtzee_service.py
# Tests for yahtzee/service.py: in-memory game state, bank integration,
# quick_play idempotency, full 13-round flow, disconnect cleanup.

import random
from unittest.mock import MagicMock, patch

import pytest

from casino.yahtzee import lib
from casino.yahtzee.dealer import YahtzeeDealer
from casino.yahtzee.service import YahtzeeGame, YahtzeeService


def _make_args():
    return MagicMock()


def _mock_table_service(table_moniker="yahtzee-alice"):
    ts = MagicMock()
    ts.create_table.return_value = {
        "success": True,
        "table": {
            "moniker": table_moniker,
            "type": "yahtzee",
            "minimumbet": 10,
            "maximumbet": 1000,
            "ownermoniker": "alice",
            "status": "open",
            "hidden": True,
            "accountid": 1,
        },
        "message": "ok",
    }
    return ts


def _make_service(find_returns=None):
    """Build a YahtzeeService with all DB-touching deps mocked out.

    ``find_returns`` is what the injected find_table_fn returns for
    any player (default: None, which means "no existing table").
    """
    args = _make_args()
    ts = _mock_table_service()
    dealer = YahtzeeDealer(rng=random.Random(0))
    find_fn = MagicMock(return_value=find_returns)
    s = YahtzeeService(
        args,
        dealer=dealer,
        table_service=ts,
        find_table_fn=find_fn,
    )
    return s, ts, find_fn


def _seed_quick_play(s):
    """Run quick_play with the dal_* functions mocked. Returns the mocks.

    The mocks remain in effect for the rest of the test (the patches
    are started and ``stop()`` is exposed via ``_patch_handles`` on
    the test instance so teardown can call them). Tests that need
    to make multiple quick_play calls must keep the patches active.
    """
    db = MagicMock()
    dg = MagicMock()
    dbconn = MagicMock()
    dg.create_game.return_value = {"id": 42}
    db.place_bet.return_value = {"id": 7}
    p1 = patch("casino.yahtzee.service.dal_bet", db)
    p2 = patch("casino.yahtzee.service.dal_game", dg)
    p3 = patch("casino.yahtzee.service.database", dbconn)
    p1.start()
    p2.start()
    p3.start()
    s.quick_play("alice")
    s._patch_handles = (p1, p2, p3)
    s._db_mocks = (db, dg, dbconn)
    return db, dg, dbconn


def _stop_patches(s):
    for p in getattr(s, "_patch_handles", ()):
        p.stop()


class TestYahtzeeGame:
    def test_state_dict_shape(self):
        g = YahtzeeGame(
            table_moniker="yahtzee-alice", player_moniker="alice",
            game_id=1, bet_id=2, bet_amount=10,
        )
        s = g.state_dict()
        assert s["table_moniker"] == "yahtzee-alice"
        assert s["round"] == 0
        assert s["dice"] == [0, 0, 0, 0, 0]
        assert s["locked"] == [False] * 5
        assert s["rolls_left"] == 2
        assert s["running_total"] == 0
        assert s["last_score"] == 0
        assert s["is_over"] is False
        assert set(s["scorecard"].keys()) == set(lib.CATEGORIES)
        for v in s["scorecard"].values():
            assert v is None

    def test_result_dict_shape(self):
        g = YahtzeeGame(
            table_moniker="t", player_moniker="p",
            game_id=1, bet_id=2, bet_amount=10,
        )
        g.scorecard = {c: 5 for c in lib.CATEGORIES}
        r = g.result_dict()
        assert r["upper_total"] == 30
        assert r["lower_total"] == 35
        assert r["grand_total"] == 65
        assert r["rake_total"] == 0


class TestQuickPlay:
    def test_first_call_creates_table_and_game(self):
        s, ts, find_fn = _make_service(find_returns=None)
        db, dg, dbconn = _seed_quick_play(s)
        try:
            assert ts.create_table.call_count == 1
            assert dg.create_game.call_count == 1
            assert db.place_bet.call_count == 1
            assert s.get_game("yahtzee-alice") is not None
            call = db.place_bet.call_args
            assert call.kwargs["amount"] == 10
            assert call.kwargs["notes"] == "yahtzee_v1"
        finally:
            _stop_patches(s)

    def test_idempotent_when_game_active(self):
        s, ts, find_fn = _make_service(find_returns=None)
        db, dg, dbconn = _seed_quick_play(s)
        try:
            ts.create_table.reset_mock()
            dg.create_game.reset_mock()
            db.place_bet.reset_mock()
            state = s.quick_play("alice")
            ts.create_table.assert_not_called()
            dg.create_game.assert_not_called()
            db.place_bet.assert_not_called()
            # Active game exists; state reflects round 0 of it
            assert state["round"] == 0
        finally:
            _stop_patches(s)

    def test_reuses_existing_open_table(self):
        existing = {
            "moniker": "yahtzee-alice", "type": "yahtzee",
            "minimumbet": 10, "maximumbet": 1000,
            "ownermoniker": "alice", "status": "open",
            "hidden": True, "accountid": 1,
        }
        s, ts, find_fn = _make_service(find_returns=existing)
        db, dg, dbconn = _seed_quick_play(s)
        try:
            ts.create_table.assert_not_called()
            dg.create_game.assert_called_once()
            db.place_bet.assert_called_once()
        finally:
            _stop_patches(s)

    def test_insufficient_funds_cancels_game(self):
        s, ts, find_fn = _make_service(find_returns=None)
        db = MagicMock()
        dg = MagicMock()
        dbconn = MagicMock()
        dg.create_game.return_value = {"id": 42}
        db.place_bet.side_effect = ValueError("Insufficient funds")
        with patch("casino.yahtzee.service.dal_bet", db), \
             patch("casino.yahtzee.service.dal_game", dg), \
             patch("casino.yahtzee.service.database", dbconn):
            with pytest.raises(ValueError):
                s.quick_play("alice")
        dg.update_game_status.assert_called_once_with(s.args, 42, "cancelled")
        assert s.get_game("yahtzee-alice") is None


class TestRollAndReroll:
    def _seed(self, s, seed=1):
        s._dealer = YahtzeeDealer(rng=random.Random(seed))
        _seed_quick_play(s)

    def test_roll_decrements_rolls_left(self):
        s, _, _ = _make_service()
        self._seed(s)
        try:
            state = s.roll("yahtzee-alice", "alice")
            assert state["rolls_left"] == 1
            assert len(state["dice"]) == 5
            for d in state["dice"]:
                assert 1 <= d <= 6
        finally:
            _stop_patches(s)

    def test_roll_at_wrong_time_errors(self):
        s, _, _ = _make_service()
        self._seed(s)
        try:
            s.roll("yahtzee-alice", "alice")
            s.roll("yahtzee-alice", "alice")  # rolls_left is now 1
            result = s.roll("yahtzee-alice", "alice")
            assert result["type"] == "error"
            assert result["code"] == "not_at_start_of_round"
        finally:
            _stop_patches(s)

    def test_reroll_with_locks(self):
        s, _, _ = _make_service()
        self._seed(s)
        try:
            s.roll("yahtzee-alice", "alice")
            state = s.reroll("yahtzee-alice", "alice", [0, 1, 2, 3, 4])
            assert state["rolls_left"] == 0
            assert state["locked"] == [True] * 5
            result = s.reroll("yahtzee-alice", "alice", [0, 1, 2, 3, 4])
            assert result["type"] == "error"
            assert result["code"] == "no_rolls_left"
        finally:
            _stop_patches(s)

    def test_reroll_bad_locks(self):
        s, _, _ = _make_service()
        self._seed(s)
        try:
            s.roll("yahtzee-alice", "alice")
            result = s.reroll("yahtzee-alice", "alice", [0, 5])
            assert result["type"] == "error"
            assert result["code"] == "bad_locks"
        finally:
            _stop_patches(s)

    def test_reroll_wrong_player(self):
        s, _, _ = _make_service()
        self._seed(s)
        try:
            s.roll("yahtzee-alice", "alice")
            with pytest.raises(PermissionError):
                s.reroll("yahtzee-alice", "bob", [0])
        finally:
            _stop_patches(s)

    def test_reroll_no_active_game(self):
        s, _, _ = _make_service()
        with pytest.raises(KeyError):
            s.reroll("yahtzee-alice", "alice", [0])


class TestScoreAndFullSession:
    def _seed(self, s, seed=4):
        s._dealer = YahtzeeDealer(rng=random.Random(seed))
        _seed_quick_play(s)

    def test_rejects_unknown_category(self):
        s, _, _ = _make_service()
        self._seed(s)
        try:
            s.roll("yahtzee-alice", "alice")
            result = s.score("yahtzee-alice", "alice", "bogus")
            assert result["type"] == "error"
            assert result["code"] == "bad_category"
        finally:
            _stop_patches(s)

    def test_rejects_used_category(self):
        s, _, _ = _make_service()
        self._seed(s)
        try:
            s.roll("yahtzee-alice", "alice")
            s.score("yahtzee-alice", "alice", "ones")
            s.roll("yahtzee-alice", "alice")
            result = s.score("yahtzee-alice", "alice", "ones")
            assert result["type"] == "error"
            assert result["code"] == "category_used"
        finally:
            _stop_patches(s)

    def test_early_score_after_one_roll(self):
        s, _, _ = _make_service()
        self._seed(s)
        try:
            s.roll("yahtzee-alice", "alice")
            with patch("casino.yahtzee.service.dal_bet") as db, \
                 patch("casino.yahtzee.service.database"):
                result = s.score("yahtzee-alice", "alice", "chance")
                assert result["type"] == "yahtzee_state"
                assert result["round"] == 1
                db.settle_bet.assert_called_once()
        finally:
            _stop_patches(s)

    def test_full_13_round_session(self):
        s, _, _ = _make_service()
        s._dealer = YahtzeeDealer(rng=random.Random(99))
        db, dg, dbconn = _seed_quick_play(s)

        settle_calls = []

        def fake_settle(*args, **kwargs):
            settle_calls.append(kwargs)

        log_calls = []

        def fake_query(q, **kw):
            log_calls.append(kw)
            return q
        dbconn.query.side_effect = fake_query

        fake_cursor = MagicMock()
        fake_cursor.__enter__.return_value = fake_cursor
        fake_cursor.__exit__.return_value = False
        dbconn.cursor.return_value = fake_cursor

        # Replace the Jsonb import in the service module with an identity
        # function so attrs come through as plain dicts in log_calls.
        from casino.yahtzee import service as svc
        with patch.object(svc, "Jsonb", side_effect=lambda d: d):
            db.settle_bet.side_effect = fake_settle

            try:
                for round_num, category in enumerate(lib.CATEGORIES):
                    s.roll("yahtzee-alice", "alice")
                    result = s.score("yahtzee-alice", "alice", category)
                    if round_num < 12:
                        assert result["type"] == "yahtzee_state", f"round {round_num} got {result}"
                        assert result["round"] == round_num + 1
                    else:
                        assert result["type"] == "yahtzee_result"

                assert len(settle_calls) == 13
                for c in settle_calls:
                    assert c["bet_id"] == 7
                    assert c["won"] is (c["payout"] > 0)
                    assert 0 <= c["payout"] <= 30
                assert len(log_calls) == 13
                for k in log_calls:
                    assert k["message"] == "yahtzee_turn"
                    assert k["attrs"]["rake"] == 0
                assert dg.update_game_status.call_count == 1
                assert dg.update_game_status.call_args.args[2] == "closed"
                assert s.get_game("yahtzee-alice") is None
            finally:
                _stop_patches(s)


class TestDisconnectCleanup:
    def test_finalize_settles_loss_and_removes_game(self):
        s, _, _ = _make_service()
        _seed_quick_play(s)
        try:
            assert s.get_game("yahtzee-alice") is not None
            with patch("casino.yahtzee.service.dal_bet") as db, \
                 patch("casino.yahtzee.service.dal_game") as dg:
                result = s.finalize_on_disconnect("yahtzee-alice")
                assert result is True
                db.settle_bet.assert_called_once_with(
                    s.args, bet_id=7, won=False, payout=0,
                )
                dg.update_game_status.assert_called_once_with(s.args, 42, "cancelled")
                assert s.get_game("yahtzee-alice") is None
        finally:
            _stop_patches(s)

    def test_finalize_returns_false_when_no_game(self):
        s, _, _ = _make_service()
        assert s.finalize_on_disconnect("nonexistent") is False


class TestDefaultFindTable:
    """Smoke test the default find function; just ensure it queries the
    right table and returns None when fetchone returns None."""

    def test_returns_none_when_no_row(self):
        from casino.yahtzee import service as svc
        args = _make_args()
        class _C:
            def __enter__(self_inner): return self_inner
            def __exit__(self_inner, *a): return False
            def execute(self_inner, q, **kwargs): pass
            def fetchone(self_inner): return None
        class _Conn:
            def __enter__(self_inner): return self_inner
            def __exit__(self_inner, *a): return False
            def cursor(self_inner): return _C()
        with patch.object(svc.database, "connect", return_value=_Conn()), \
             patch.object(svc.database, "cursor", return_value=_C()), \
             patch.object(svc.database, "query", side_effect=lambda q, **k: q):
            assert svc._default_find_table(args, "alice") is None
