# casino/tests/test_tictactoe_service.py
# Tests for tictactoe/service.py: in-memory game state, mode handling,
# bank integration, AI replies, mode-0 self-play, disconnect cleanup.

from unittest.mock import MagicMock, patch

import pytest

from casino.tictactoe import lib
from casino.tictactoe.dealer import TictactoeDealer
from casino.tictactoe.service import AI_O, AI_X, TictactoeGame, TictactoeService

# ---------- helpers ----------

def _make_args():
    return MagicMock()


def _mock_table_service(table_moniker="ttt-alice"):
    ts = MagicMock()
    ts.create_table.return_value = {
        "success": True,
        "table": {
            "moniker": table_moniker,
            "type": "tictactoe",
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
    args = _make_args()
    ts = _mock_table_service()
    dealer = TictactoeDealer()
    find_fn = MagicMock(return_value=find_returns)
    s = TictactoeService(
        args,
        dealer=dealer,
        table_service=ts,
        find_table_fn=find_fn,
    )
    return s, ts, find_fn


def _seed_quick_play(s, mode=1):
    """Run quick_play with the dal_* functions and database mocked.

    Returns (db_mock, dg_mock, dbconn_mock). The patches are stored
    on ``s`` via ``_patch_handles`` for later teardown.
    """
    db = MagicMock()
    dg = MagicMock()
    dbconn = MagicMock()
    dg.create_game.return_value = {"id": 42}
    db.place_bet.return_value = {"id": 7}
    p1 = patch("casino.tictactoe.service.dal_bet", db)
    p2 = patch("casino.tictactoe.service.dal_game", dg)
    p3 = patch("casino.tictactoe.service.database", dbconn)
    p1.start()
    p2.start()
    p3.start()
    s.quick_play("alice", mode=mode)
    s._patch_handles = (p1, p2, p3)
    s._db_mocks = (db, dg, dbconn)
    return db, dg, dbconn


def _stop_patches(s):
    for p in getattr(s, "_patch_handles", ()):
        p.stop()


# ---------- TictactoeGame dataclass ----------

class TestTictactoeGame:
    def test_state_dict_shape(self):
        g = TictactoeGame(
            table_moniker="ttt-alice", mode=1,
            players=["alice", AI_O], game_id=1, bet_id=2, bet_amount=10,
        )
        s = g.state_dict()
        assert s["table_moniker"] == "ttt-alice"
        assert s["mode"] == 1
        assert s["board"] == [0] * 9
        assert s["to_move"] == lib.X
        assert s["turn_moniker"] == "alice"
        assert s["winner"] is None
        assert s["is_over"] is False
        assert s["moves_played"] == 0
        assert s["last_move"] is None

    def test_state_dict_after_move(self):
        g = TictactoeGame(
            table_moniker="t", mode=1,
            players=["alice", AI_O], game_id=1, bet_id=2, bet_amount=10,
        )
        g.board = g.board.with_move(4, lib.X)
        g.moves_played = 1
        g.last_move = {"cell": 4, "mark": lib.X, "by": "alice"}
        s = g.state_dict()
        assert s["to_move"] == lib.O
        assert s["turn_moniker"] == AI_O
        assert s["moves_played"] == 1
        assert s["last_move"] == {"cell": 4, "mark": lib.X, "by": "alice"}

    def test_result_dict_shape(self):
        g = TictactoeGame(
            table_moniker="t", mode=1,
            players=["alice", AI_O], game_id=1, bet_id=2, bet_amount=10,
        )
        g.board = lib.Board(
            cells=[1, 1, 1, 0, 2, 0, 0, 0, 2],
            to_move=lib.O,
            winner=lib.X,
        )
        r = g.result_dict(payout_amount=20, new_balance=120)
        assert r["winner"] == lib.X
        assert r["winner_moniker"] == "alice"
        assert r["is_draw"] is False
        assert r["payout"] == 20
        assert r["new_balance"] == 120
        assert r["rake"] == 0

    def test_result_dict_draw(self):
        g = TictactoeGame(
            table_moniker="t", mode=0,
            players=[AI_X, AI_O], game_id=1, bet_id=2, bet_amount=10,
        )
        g.board = lib.Board(
            cells=[1, 2, 1, 2, 1, 2, 2, 1, 2],
            to_move=lib.O,
            winner=lib.DRAW,
        )
        r = g.result_dict(payout_amount=0, new_balance=0)
        assert r["winner"] == 0
        assert r["winner_moniker"] is None
        assert r["is_draw"] is True

    def test_mode_0_requires_ai_players(self):
        with pytest.raises(ValueError, match="mode 0"):
            TictactoeGame(
                table_moniker="t", mode=0,
                players=["alice", AI_O],  # wrong
                game_id=1, bet_id=2, bet_amount=10,
            )

    def test_mode_1_requires_human_x_and_ai_o(self):
        with pytest.raises(ValueError, match="mode 1"):
            TictactoeGame(
                table_moniker="t", mode=1,
                players=[AI_X, AI_O],  # wrong
                game_id=1, bet_id=2, bet_amount=10,
            )

    def test_mode_2_cannot_have_ai_players(self):
        with pytest.raises(ValueError, match="mode 2"):
            TictactoeGame(
                table_moniker="t", mode=2,
                players=["alice", AI_O],  # wrong
                game_id=1, bet_id=2, bet_amount=10,
            )

    def test_bad_mode_raises(self):
        with pytest.raises(ValueError, match="mode must be"):
            TictactoeGame(
                table_moniker="t", mode=5,
                players=["alice", "bob"], game_id=1, bet_id=2, bet_amount=10,
            )


# ---------- quick_play ----------

class TestQuickPlay:
    def test_first_call_creates_table_and_game_mode_1(self):
        s, ts, find_fn = _make_service(find_returns=None)
        db, dg, dbconn = _seed_quick_play(s, mode=1)
        try:
            assert ts.create_table.call_count == 1
            assert dg.create_game.call_count == 1
            assert db.place_bet.call_count == 1
            assert s.get_game("ttt-alice") is not None
            call = db.place_bet.call_args
            assert call.kwargs["amount"] == 10
            assert "tictactoe_v1_mode1" in call.kwargs["notes"]
        finally:
            _stop_patches(s)

    def test_first_call_mode_0(self):
        s, ts, find_fn = _make_service(find_returns=None)
        db, dg, dbconn = _seed_quick_play(s, mode=0)
        try:
            g = s.get_game("ttt-alice")
            assert g is not None
            assert g.mode == 0
            assert g.players == [AI_X, AI_O]
        finally:
            _stop_patches(s)

    def test_first_call_mode_2(self):
        s, ts, find_fn = _make_service(find_returns=None)
        db, dg, dbconn = _seed_quick_play(s, mode=2)
        try:
            g = s.get_game("ttt-alice")
            assert g is not None
            assert g.mode == 2
            assert g.players[0] == "alice"
            # O seat is awaiting opponent in mode 2
            assert g.players[1] == "__awaiting_opponent__"
        finally:
            _stop_patches(s)

    def test_quick_play_bad_mode(self):
        s, ts, find_fn = _make_service()
        result = s.quick_play("alice", mode=5)
        assert result["type"] == "error"
        assert result["code"] == "bad_mode"

    def test_idempotent_when_game_active(self):
        s, ts, find_fn = _make_service(find_returns=None)
        db, dg, dbconn = _seed_quick_play(s, mode=1)
        try:
            ts.create_table.reset_mock()
            dg.create_game.reset_mock()
            db.place_bet.reset_mock()
            state = s.quick_play("alice", mode=1)
            ts.create_table.assert_not_called()
            dg.create_game.assert_not_called()
            db.place_bet.assert_not_called()
            assert state["moves_played"] == 0
        finally:
            _stop_patches(s)

    def test_reuses_existing_open_table(self):
        existing = {
            "moniker": "ttt-alice", "type": "tictactoe",
            "minimumbet": 10, "maximumbet": 1000,
            "ownermoniker": "alice", "status": "open",
            "hidden": True, "accountid": 1,
        }
        s, ts, find_fn = _make_service(find_returns=existing)
        db, dg, dbconn = _seed_quick_play(s, mode=1)
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
        with patch("casino.tictactoe.service.dal_bet", db), \
             patch("casino.tictactoe.service.dal_game", dg), \
             patch("casino.tictactoe.service.database", dbconn), pytest.raises(ValueError):
            s.quick_play("alice", mode=1)
        dg.update_game_status.assert_called_once_with(s.args, 42, "cancelled")
        assert s.get_game("ttt-alice") is None


# ---------- play_move (human + AI reply) ----------

class TestPlayMoveMode1:
    def _seed(self, s):
        _seed_quick_play(s, mode=1)

    def test_human_move_advances_and_triggers_ai(self):
        s, _, _ = _make_service()
        self._seed(s)
        try:
            with patch("casino.tictactoe.service.dal_bet") as _db, \
                 patch("casino.tictactoe.service.database"):
                result = s.play_move("ttt-alice", "alice", 4)
                assert result["type"] == "tictactoe_state"
                # Alice played 4, then AI O played somewhere
                assert result["moves_played"] == 2
                assert result["board"][4] == lib.X
                # O played somewhere
                o_cells = [i for i, c in enumerate(result["board"]) if c == lib.O]
                assert len(o_cells) == 1
                # AI's move was the last_move
                assert result["last_move"]["by"] == AI_O
        finally:
            _stop_patches(s)

    def test_invalid_cell_returns_error(self):
        s, _, _ = _make_service()
        self._seed(s)
        try:
            with patch("casino.tictactoe.service.dal_bet"), \
                 patch("casino.tictactoe.service.database"):
                r = s.play_move("ttt-alice", "alice", 99)
                assert r["type"] == "error"
                assert r["code"] == "cell_out_of_range"
        finally:
            _stop_patches(s)

    def test_occupied_cell_returns_error(self):
        s, _, _ = _make_service()
        self._seed(s)
        try:
            with patch("casino.tictactoe.service.dal_bet") as _db, \
                 patch("casino.tictactoe.service.database"):
                s.play_move("ttt-alice", "alice", 4)
                r = s.play_move("ttt-alice", "alice", 4)
                assert r["type"] == "error"
                assert r["code"] == "cell_occupied"
        finally:
            _stop_patches(s)

    def test_not_your_turn(self):
        s, _, _ = _make_service()
        self._seed(s)
        try:
            with patch("casino.tictactoe.service.dal_bet"), \
                 patch("casino.tictactoe.service.database"):
                # After Alice's first move, it's AI_O's turn; bob can't move
                s.play_move("ttt-alice", "alice", 0)
                r = s.play_move("ttt-alice", "bob", 1)
                assert r["type"] == "error"
                assert r["code"] == "not_your_turn"
        finally:
            _stop_patches(s)

    def test_winning_move_settles(self):
        s, _, _ = _make_service()
        self._seed(s)
        try:
            with patch("casino.tictactoe.service.dal_bet") as db, \
                 patch("casino.tictactoe.service.database"), \
                 patch("casino.tictactoe.service.dal_game") as dg:
                # Play out a sequence where X wins. We'll set up the board
                # so Alice's next move completes a 3-in-a-row.
                # First, force a known state by playing 0 (X) and 3 (O).
                s.play_move("ttt-alice", "alice", 0)
                # After this, X is at 0, O is somewhere (AI). Force
                # the O move to 3 to keep the test deterministic. We do
                # that by overriding the dealer briefly.
                g = s.get_game("ttt-alice")
                g.board = lib.Board(
                    cells=[1, 0, 0, 0, 0, 0, 0, 0, 0],
                    to_move=lib.O,
                    winner=None,
                )
                g.last_move = {"cell": 0, "mark": lib.X, "by": "alice"}
                # Manually set O to cell 3 (opponent's prior move)
                g.board = g.board.with_move(3, lib.O)
                g.last_move = {"cell": 3, "mark": lib.O, "by": AI_O}
                # Now Alice plays 1 (X to move). With cell 0 and 1 X'd, she
                # threatens 2; but we also want to test "win completes",
                # so we need X to have 0 and 1 and then play 2.
                # Actually current state: X=0, O=3. Alice plays 1, then AI
                # will play somewhere. We need to test "winning move" path,
                # so set up: X=0, X=1 (already), then Alice plays 2.
                g.board = lib.Board(
                    cells=[1, 1, 0, 2, 0, 0, 0, 0, 0],
                    to_move=lib.X,
                    winner=None,
                )
                # Alice now plays 2 to win
                result = s.play_move("ttt-alice", "alice", 2)
                assert result["type"] == "tictactoe_result"
                assert result["winner"] == lib.X
                assert result["winner_moniker"] == "alice"
                assert result["payout"] == 20  # bet*2
                db.settle_bet.assert_called_once()
                args, kwargs = db.settle_bet.call_args
                assert kwargs["won"] is True
                assert kwargs["payout"] == 20
                dg.update_game_status.assert_called_once()
                assert s.get_game("ttt-alice") is None
        finally:
            _stop_patches(s)

    def test_draw_refunds(self):
        s, _, _ = _make_service()
        self._seed(s)
        try:
            with patch("casino.tictactoe.service.dal_bet") as db, \
                 patch("casino.tictactoe.service.database"), \
                 patch("casino.tictactoe.service.dal_game"):
                # Set up a position where Alice's next move is the last
                # cell and it produces a draw (no winner). The board
                # before her move: X=0,2,3,7; O=1,4,5,6; cell 8 empty.
                # No row, column, or diagonal is a 3-in-a-row.
                g = s.get_game("ttt-alice")
                g.board = lib.Board(
                    cells=[1, 2, 1, 1, 2, 2, 2, 1, 0],
                    to_move=lib.X,
                    winner=None,
                )
                # Alice plays 8 -> draw
                result = s.play_move("ttt-alice", "alice", 8)
                assert result["type"] == "tictactoe_result"
                assert result["winner"] == 0
                assert result["is_draw"] is True
                # Push: payout == bet
                assert result["payout"] == 10
                db.settle_bet.assert_called_once()
                args, kwargs = db.settle_bet.call_args
                assert kwargs["won"] is True
                assert kwargs["payout"] == 10
        finally:
            _stop_patches(s)

    def test_no_active_game(self):
        s, _, _ = _make_service()
        with patch("casino.tictactoe.service.dal_bet"), \
             patch("casino.tictactoe.service.database"):
            r = s.play_move("nonexistent", "alice", 0)
            assert r["type"] == "error"
            assert r["code"] == "not_at_table"

    def test_cell_must_be_int(self):
        s, _, _ = _make_service()
        self._seed(s)
        try:
            with patch("casino.tictactoe.service.dal_bet"), \
                 patch("casino.tictactoe.service.database"):
                r = s.play_move("ttt-alice", "alice", "0")
                assert r["type"] == "error"
                assert r["code"] == "cell_out_of_range"
        finally:
            _stop_patches(s)


# ---------- mode 0 (2 AI, server self-play) ----------

class TestMode0:
    def test_quick_play_creates_ai_game(self):
        s, _, _ = _make_service()
        _seed_quick_play(s, mode=0)
        try:
            g = s.get_game("ttt-alice")
            assert g is not None
            assert g.mode == 0
            assert g.players == [AI_X, AI_O]
        finally:
            _stop_patches(s)

    def test_human_move_rejected(self):
        s, _, _ = _make_service()
        _seed_quick_play(s, mode=0)
        try:
            with patch("casino.tictactoe.service.dal_bet"), \
                 patch("casino.tictactoe.service.database"):
                r = s.play_move("ttt-alice", "alice", 0)
                assert r["type"] == "error"
                assert r["code"] == "wrong_mode_for_action"
        finally:
            _stop_patches(s)

    def test_auto_play_to_completion(self):
        s, _, _ = _make_service()
        _seed_quick_play(s, mode=0)
        try:
            with patch("casino.tictactoe.service.dal_bet") as db, \
                 patch("casino.tictactoe.service.database"), \
                 patch("casino.tictactoe.service.dal_game") as dg:
                states = s.auto_play_mode0("ttt-alice")
                # 5 X moves, 4 O moves, 9 total, last is tictactoe_result
                assert len(states) >= 5
                # Last is a result
                assert states[-1]["type"] == "tictactoe_result"
                # Perfect vs perfect = draw
                assert states[-1]["winner"] == 0
                db.settle_bet.assert_called_once()
                args, kwargs = db.settle_bet.call_args
                assert kwargs["won"] is True
                assert kwargs["payout"] == 10  # push
                dg.update_game_status.assert_called_once()
                assert s.get_game("ttt-alice") is None
        finally:
            _stop_patches(s)

    def test_resign_rejected_in_mode0(self):
        s, _, _ = _make_service()
        _seed_quick_play(s, mode=0)
        try:
            with patch("casino.tictactoe.service.dal_bet"), \
                 patch("casino.tictactoe.service.database"):
                r = s.resign("ttt-alice", "alice")
                assert r["type"] == "error"
                assert r["code"] == "wrong_mode_for_action"
        finally:
            _stop_patches(s)


# ---------- mode 2 (2 humans) ----------

class TestMode2:
    def test_join_takes_o_seat(self):
        s, _, _ = _make_service()
        _seed_quick_play(s, mode=2)
        try:
            r = s.join("ttt-alice", "bob")
            assert r["type"] == "tictactoe_state"
            g = s.get_game("ttt-alice")
            assert g.players == ["alice", "bob"]
        finally:
            _stop_patches(s)

    def test_join_rejects_when_table_full(self):
        s, _, _ = _make_service()
        _seed_quick_play(s, mode=2)
        try:
            s.join("ttt-alice", "bob")
            r = s.join("ttt-alice", "carol")
            assert r["type"] == "error"
            assert r["code"] == "table_full"
        finally:
            _stop_patches(s)

    def test_join_rejects_owner(self):
        s, _, _ = _make_service()
        _seed_quick_play(s, mode=2)
        try:
            r = s.join("ttt-alice", "alice")
            assert r["type"] == "error"
            assert r["code"] == "not_your_seat"
        finally:
            _stop_patches(s)

    def test_join_rejected_in_mode_1(self):
        s, _, _ = _make_service()
        _seed_quick_play(s, mode=1)
        try:
            r = s.join("ttt-alice", "bob")
            assert r["type"] == "error"
            assert r["code"] == "wrong_mode_for_action"
        finally:
            _stop_patches(s)

    def test_2_humans_alternate_turns(self):
        s, _, _ = _make_service()
        _seed_quick_play(s, mode=2)
        try:
            s.join("ttt-alice", "bob")
            with patch("casino.tictactoe.service.dal_bet"), \
                 patch("casino.tictactoe.service.database"):
                # Out-of-turn on the very first move: bob tries while it's
                # Alice's (X) turn -> error.
                r0 = s.play_move("ttt-alice", "bob", 1)
                assert r0["type"] == "error"
                assert r0["code"] == "not_your_turn"
                # Alice (X) plays 0
                r1 = s.play_move("ttt-alice", "alice", 0)
                assert r1["type"] == "tictactoe_state"
                assert r1["moves_played"] == 1
                assert r1["turn_moniker"] == "bob"  # O's turn
                # Out-of-turn: alice tries while it's bob's (O) turn -> error
                r1b = s.play_move("ttt-alice", "alice", 2)
                assert r1b["type"] == "error"
                assert r1b["code"] == "not_your_turn"
                # Now bob's turn
                r2 = s.play_move("ttt-alice", "bob", 1)
                assert r2["type"] == "tictactoe_state"
                assert r2["moves_played"] == 2
                assert r2["turn_moniker"] == "alice"  # X's turn
        finally:
            _stop_patches(s)

    def test_resign_settles_loss(self):
        s, _, _ = _make_service()
        _seed_quick_play(s, mode=2)
        try:
            s.join("ttt-alice", "bob")
            with patch("casino.tictactoe.service.dal_bet") as db, \
                 patch("casino.tictactoe.service.database"), \
                 patch("casino.tictactoe.service.dal_game") as dg:
                r = s.resign("ttt-alice", "alice")
                assert r["type"] == "tictactoe_result"
                # Alice resigned; bob (O) wins
                assert r["winner"] == lib.O
                assert r["winner_moniker"] == "bob"
                # bettor is X (alice), so she loses -> payout 0
                assert r["payout"] == 0
                db.settle_bet.assert_called_once()
                args, kwargs = db.settle_bet.call_args
                assert kwargs["won"] is False
                assert kwargs["payout"] == 0
                dg.update_game_status.assert_called_once()
                assert s.get_game("ttt-alice") is None
        finally:
            _stop_patches(s)


# ---------- disconnect cleanup ----------

class TestFinalizeOnDisconnect:
    def test_mode1_disconnect_settles_loss(self):
        s, _, _ = _make_service()
        _seed_quick_play(s, mode=1)
        try:
            with patch("casino.tictactoe.service.dal_bet") as db, \
                 patch("casino.tictactoe.service.database"), \
                 patch("casino.tictactoe.service.dal_game") as dg:
                # Alice makes one move, then disconnects
                s.play_move("ttt-alice", "alice", 0)
                result = s.finalize_on_disconnect("ttt-alice", "alice")
                assert result is True
                # Alice was X; she loses on disconnect -> payout 0
                db.settle_bet.assert_called()
                last_kwargs = db.settle_bet.call_args.kwargs
                assert last_kwargs["won"] is False
                assert last_kwargs["payout"] == 0
                dg.update_game_status.assert_called()
                assert s.get_game("ttt-alice") is None
        finally:
            _stop_patches(s)

    def test_mode0_disconnect_ignored(self):
        s, _, _ = _make_service()
        _seed_quick_play(s, mode=0)
        try:
            with patch("casino.tictactoe.service.dal_bet"), \
                 patch("casino.tictactoe.service.database"):
                result = s.finalize_on_disconnect("ttt-alice", "alice")
                assert result is False
        finally:
            _stop_patches(s)

    def test_no_game_returns_false(self):
        s, _, _ = _make_service()
        assert s.finalize_on_disconnect("nonexistent") is False

    def test_already_over_returns_false(self):
        s, _, _ = _make_service()
        _seed_quick_play(s, mode=1)
        try:
            with patch("casino.tictactoe.service.dal_bet"), \
                 patch("casino.tictactoe.service.database"):
                # Set is_over directly
                g = s.get_game("ttt-alice")
                g.is_over = True
                assert s.finalize_on_disconnect("ttt-alice", "alice") is False
        finally:
            _stop_patches(s)


# ---------- _default_find_table ----------

class TestDefaultFindTable:
    def test_returns_none_when_no_row(self):
        from casino.tictactoe import service as svc
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
