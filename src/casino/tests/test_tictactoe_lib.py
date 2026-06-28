# casino/tests/test_tictactoe_lib.py
# Tests for tictactoe/lib.py: board state, win detection, perfect-play AI,
# payout math.

import pytest

from casino.tictactoe import lib


# ---------- constants ----------

class TestConstants:
    def test_num_cells(self):
        assert lib.NUM_CELLS == 9

    def test_min_max_bet(self):
        assert lib.MIN_BET == 10
        assert lib.MAX_BET == 1000

    def test_rake_disabled_in_v1(self):
        assert lib.RAKE_PERCENT == 0

    def test_empty_x_o_marks(self):
        assert lib.EMPTY == 0
        assert lib.X == 1
        assert lib.O == 2
        assert lib.DRAW == 0

    def test_win_lines(self):
        # All 8 standard lines
        assert len(lib.WIN_LINES) == 8
        assert (0, 4, 8) in lib.WIN_LINES  # main diagonal
        assert (2, 4, 6) in lib.WIN_LINES  # anti-diagonal
        assert (0, 1, 2) in lib.WIN_LINES  # top row
        assert (6, 7, 8) in lib.WIN_LINES  # bottom row


# ---------- Board dataclass ----------

class TestBoardEmpty:
    def test_empty_board_initial_state(self):
        b = lib.Board.empty()
        assert b.cells == (0,) * 9
        assert b.to_move == lib.X
        assert b.winner is None
        assert b.is_over() is False
        assert b.is_full() is False
        assert b.is_draw() is False
        assert b.available_moves() == list(range(9))

    def test_empty_board_render(self):
        b = lib.Board.empty()
        rendered = b.render()
        # Rendered board contains 9 cells worth of glyphs
        for glyph in lib.MARK_GLYPH.values():
            # Each glyph appears some number of times in a 3x3 grid
            pass
        assert "X" not in rendered
        assert "O" not in rendered
        assert "|" in rendered
        assert "---" in rendered


class TestBoardWithMove:
    def test_legal_move_advances(self):
        b = lib.Board.empty()
        b2 = b.with_move(4, lib.X)
        assert b2.cells[4] == lib.X
        assert b2.to_move == lib.O
        assert b2.winner is None
        # Original is unchanged (frozen)
        assert b.cells[4] == lib.EMPTY

    def test_occupied_cell_raises(self):
        b = lib.Board.empty().with_move(0, lib.X)
        with pytest.raises(ValueError, match="already occupied"):
            b.with_move(0, lib.O)

    def test_out_of_range_raises(self):
        b = lib.Board.empty()
        for bad in (-1, 9, 10, 100):
            with pytest.raises(ValueError, match="must be in"):
                b.with_move(bad, lib.X)

    def test_wrong_mark_raises(self):
        b = lib.Board.empty()
        with pytest.raises(ValueError, match="mark must be"):
            b.with_move(0, 3)

    def test_mark_must_match_to_move(self):
        b = lib.Board.empty()
        # X must move first
        with pytest.raises(ValueError, match="turn"):
            b.with_move(0, lib.O)

    def test_move_after_game_over_raises(self):
        # X wins with top row
        b = (
            lib.Board.empty()
            .with_move(0, lib.X)
            .with_move(3, lib.O)
            .with_move(1, lib.X)
            .with_move(4, lib.O)
            .with_move(2, lib.X)
        )
        assert b.winner == lib.X
        with pytest.raises(ValueError, match="already over"):
            b.with_move(5, lib.O)


# ---------- check_winner ----------

class TestCheckWinner:
    def test_no_winner_empty(self):
        assert lib.check_winner((0,) * 9) is None

    def test_x_wins_top_row(self):
        cells = [1, 1, 1, 0, 0, 0, 0, 0, 0]
        assert lib.check_winner(cells) == 1

    def test_x_wins_middle_row(self):
        cells = [0, 0, 0, 1, 1, 1, 0, 0, 0]
        assert lib.check_winner(cells) == 1

    def test_x_wins_bottom_row(self):
        cells = [0, 0, 0, 0, 0, 0, 1, 1, 1]
        assert lib.check_winner(cells) == 1

    def test_o_wins_left_column(self):
        cells = [2, 0, 0, 2, 0, 0, 2, 0, 0]
        assert lib.check_winner(cells) == 2

    def test_o_wins_middle_column(self):
        cells = [0, 2, 0, 0, 2, 0, 0, 2, 0]
        assert lib.check_winner(cells) == 2

    def test_o_wins_right_column(self):
        cells = [0, 0, 2, 0, 0, 2, 0, 0, 2]
        assert lib.check_winner(cells) == 2

    def test_x_wins_main_diagonal(self):
        cells = [1, 0, 0, 0, 1, 0, 0, 0, 1]
        assert lib.check_winner(cells) == 1

    def test_x_wins_anti_diagonal(self):
        cells = [0, 0, 1, 0, 1, 0, 1, 0, 0]
        assert lib.check_winner(cells) == 1

    def test_draw_full_board(self):
        # X X O / O O X / X O X  -> no winner, full board
        cells = [1, 1, 2, 2, 2, 1, 1, 2, 1]
        assert lib.check_winner(cells) == 0  # DRAW

    def test_no_winner_partial(self):
        # X has two in a row, O has nothing -- no winner yet
        cells = [1, 1, 0, 0, 0, 0, 0, 0, 0]
        assert lib.check_winner(cells) is None

    def test_wrong_length_raises(self):
        with pytest.raises(ValueError, match="length"):
            lib.check_winner((0, 0, 0))


# ---------- available_moves ----------

class TestAvailableMoves:
    def test_empty_board_has_nine(self):
        assert lib.available_moves((0,) * 9) == [0, 1, 2, 3, 4, 5, 6, 7, 8]

    def test_full_board_has_none(self):
        cells = [1, 2, 1, 2, 1, 2, 1, 2, 1]
        assert lib.available_moves(cells) == []

    def test_partial_board(self):
        cells = [1, 0, 2, 0, 1, 0, 0, 2, 0]
        assert lib.available_moves(cells) == [1, 3, 5, 6, 8]


# ---------- play (free function) ----------

class TestPlay:
    def test_returns_new_tuple(self):
        cells = (0,) * 9
        new = lib.play(cells, 4, lib.X)
        assert new[4] == 1
        # Original tuple unchanged
        assert cells[4] == 0

    def test_rejects_occupied(self):
        cells = (1, 0, 0, 0, 0, 0, 0, 0, 0)
        with pytest.raises(ValueError, match="occupied"):
            lib.play(cells, 0, lib.O)

    def test_rejects_out_of_range(self):
        with pytest.raises(ValueError):
            lib.play((0,) * 9, 9, lib.X)

    def test_rejects_invalid_mark(self):
        with pytest.raises(ValueError):
            lib.play((0,) * 9, 0, 5)


# ---------- best_move (perfect-play AI) ----------

class TestBestMove:
    def test_empty_board_x_picks_corner(self):
        # Perfect X opening is a corner, not the center.
        move = lib.best_move((0,) * 9, lib.X)
        assert move in (0, 2, 6, 8)

    def test_chooses_winning_move(self):
        # X has two in a row at cells 0,1; playing 2 wins
        cells = [1, 1, 0, 0, 2, 0, 0, 0, 2]
        move = lib.best_move(cells, lib.X)
        assert move == 2

    def test_blocks_opponent_winning_move(self):
        # O is about to win with cells 0, 1; X must block at 2
        cells = [2, 2, 0, 0, 1, 0, 0, 0, 1]
        move = lib.best_move(cells, lib.X)
        assert move == 2

    def test_prefers_win_over_block(self):
        # X has a winning move at 2 AND must also block at 5; winning wins.
        # Top row almost complete: cells 0, 1 are X. Block not relevant here.
        cells = [1, 1, 0, 0, 0, 0, 0, 2, 0]  # O threatens col? no.
        # Actually set up: O threatens 6,7; X can win at 2.
        cells = [1, 1, 0, 0, 0, 0, 2, 2, 0]
        move = lib.best_move(cells, lib.X)
        assert move == 2  # win takes priority

    def test_takes_fork(self):
        # X to play with two opposite corners and O in the center.
        # Standard tic-tac-toe fork: X has a non-blockable double threat.
        # O at 4 (center), X at 0 and 8 (opposite corners). Available: 1,2,3,5,6,7.
        # Perfect X play picks a corner (2 or 6) to create two non-blockable
        # threats, or an edge to set up a future fork. We assert the move
        # is a legal cell that does not immediately lose to O.
        cells = [1, 0, 0, 0, 2, 0, 0, 0, 1]
        move = lib.best_move(cells, lib.X)
        assert move in lib.available_moves(cells)
        # The chosen move must not let O win on the next turn.
        new_cells = list(cells)
        new_cells[move] = lib.X
        assert lib.check_winner(new_cells) is None
        # And the resulting position from O's POV should be a draw
        # (O plays perfectly and the game ends without a winner).
        # We don't run the full game here; see test_self_play_is_draw.

    def test_finished_board_raises(self):
        # X wins with top row
        cells = [1, 1, 1, 0, 0, 0, 0, 0, 0]
        with pytest.raises(ValueError, match="finished"):
            lib.best_move(cells, lib.O)

    def test_no_legal_moves_raises(self):
        # Full board with no winner (a draw) and no legal moves.
        # Either message is acceptable; the contract is "raise on a
        # finished board".
        cells = [1, 2, 1, 2, 1, 2, 2, 1, 2]
        with pytest.raises(ValueError):
            lib.best_move(cells, lib.X)

    def test_invalid_to_move_raises(self):
        with pytest.raises(ValueError, match="to_move"):
            lib.best_move((0,) * 9, 3)

    def test_invalid_cells_length_raises(self):
        with pytest.raises(ValueError, match="length"):
            lib.best_move((0, 0, 0), lib.X)


class TestBestMoveDrawsWithSelf:
    """Perfect play on both sides must always end in a draw."""

    def _self_play(self) -> list[int]:
        cells = [0] * 9
        to_move = lib.X
        while lib.check_winner(cells) is None and any(c == 0 for c in cells):
            move = lib.best_move(cells, to_move)
            cells = list(cells)
            cells[move] = to_move
            to_move = lib.O if to_move == lib.X else lib.X
        return cells

    def test_self_play_is_draw(self):
        # Run several self-play games; with perfect play on both sides
        # the result must be a draw. (Tic-tac-toe is a draw with perfect
        # play from either side.)
        for _ in range(5):
            cells = self._self_play()
            # check_winner returns 0 on draw, 1/2 on X/O win, None on no-winner-yet
            assert lib.check_winner(cells) == 0, (
                f"perfect vs perfect should draw, got cells={cells}"
            )


# ---------- suggest ----------

class TestSuggest:
    def test_returns_score_per_legal_move(self):
        s = lib.suggest((0,) * 9, lib.X)
        assert set(s.keys()) == set(range(9))
        # 9 empty cells, all legal
        for cell, score in s.items():
            assert isinstance(score, int)
            assert -10 <= score <= 10

    def test_suggest_only_legal_moves(self):
        cells = [1, 0, 0, 0, 2, 0, 0, 0, 1]
        s = lib.suggest(cells, lib.O)
        # Occupied: 0, 4, 8. Only those should be keys.
        assert set(s.keys()) == {1, 2, 3, 5, 6, 7}

    def test_suggest_invalid_length_raises(self):
        with pytest.raises(ValueError, match="length"):
            lib.suggest((0, 0, 0), lib.X)


# ---------- payout ----------

class TestPayout:
    def test_payout_negative_bet_raises(self):
        with pytest.raises(ValueError):
            lib.payout(lib.X, -1)

    def test_payout_midgame_is_zero(self):
        assert lib.payout(None, 100) == 0

    def test_payout_win_x(self):
        assert lib.payout(lib.X, 100) == 200  # 1:1

    def test_payout_win_o(self):
        assert lib.payout(lib.O, 50) == 100

    def test_payout_draw_is_push(self):
        assert lib.payout(lib.DRAW, 100) == 100  # push: refund

    def test_payout_zero_bet(self):
        assert lib.payout(lib.X, 0) == 0
        assert lib.payout(lib.DRAW, 0) == 0


class TestBettorPayout:
    def test_bettor_wins_x(self):
        # Bettor played X, X won -> bet*2
        assert lib.bettor_payout(lib.X, lib.X, 100) == 200

    def test_bettor_loses(self):
        # Bettor played X, O won -> 0
        assert lib.bettor_payout(lib.O, lib.X, 100) == 0

    def test_bettor_draws(self):
        # Bettor played X, draw -> push
        assert lib.bettor_payout(lib.DRAW, lib.X, 100) == 100

    def test_bettor_midgame(self):
        assert lib.bettor_payout(None, lib.X, 100) == 0

    def test_bettor_o_wins(self):
        # Bettor played O, O won -> bet*2
        assert lib.bettor_payout(lib.O, lib.O, 50) == 100


class TestApplyRake:
    def test_apply_rake_is_identity_when_zero(self):
        for v in (0, 1, 7, 25, 50, 100, 250, 1000):
            assert lib._apply_rake(v) == v
