# casino/tictactoe/lib.py
# Pure engine for tic-tac-toe: board state, win detection, perfect-play AI,
# payout math. No DB, no I/O, no BED. Used by service.py and the test suite.

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

NUM_CELLS = 9
MIN_BET = 10
MAX_BET = 1000
RAKE_PERCENT = 0  # v1: 1:1 winner-takes-bet, push on draw; structure ready for v2

EMPTY = 0
X = 1
O = 2  # noqa: E741 -- intentional short name; matches tic-tac-toe notation
DRAW = 0

WIN_LINES: tuple[tuple[int, int, int], ...] = (
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),
    (0, 3, 6),
    (1, 4, 7),
    (2, 5, 8),
    (0, 4, 8),
    (2, 4, 6),
)

# Marker letters for client display.
MARK_GLYPH: dict[int, str] = {EMPTY: " ", X: "X", O: "O"}


@dataclass(frozen=True)
class Board:
    """Immutable 3x3 tic-tac-toe board.

    ``cells`` is a 9-tuple of ints in {0=empty, 1=X, 2=O}. ``to_move`` is
    the mark that plays next (1 or 2). ``winner`` is 1, 2, or 0 (DRAW);
    None while the game is in progress.
    """

    cells: tuple[int, ...]
    to_move: int
    winner: int | None = None

    @classmethod
    def empty(cls) -> Board:
        return cls(cells=(0,) * NUM_CELLS, to_move=X, winner=None)

    def is_full(self) -> bool:
        return all(c != EMPTY for c in self.cells)

    def is_over(self) -> bool:
        return self.winner is not None

    def is_draw(self) -> bool:
        return self.winner == DRAW and self.is_full()

    def available_moves(self) -> list[int]:
        return [i for i, c in enumerate(self.cells) if c == EMPTY]

    def with_move(self, cell: int, mark: int) -> Board:
        """Return a new Board with ``mark`` played at ``cell``.

        Raises ValueError if the move is illegal (out of range, occupied,
        or game already over).
        """
        if self.winner is not None:
            raise ValueError("game is already over")
        if not (0 <= cell < NUM_CELLS):
            raise ValueError(f"cell must be in [0, {NUM_CELLS}), got {cell}")
        if mark not in (X, O):
            raise ValueError(f"mark must be X ({X}) or O ({O}), got {mark}")
        if mark != self.to_move:
            raise ValueError(
                f"it is mark {self.to_move}'s turn, not {mark}'s"
            )
        if self.cells[cell] != EMPTY:
            raise ValueError(f"cell {cell} is already occupied")
        new_cells = list(self.cells)
        new_cells[cell] = mark
        new_winner = check_winner(tuple(new_cells))
        return Board(
            cells=tuple(new_cells),
            to_move=O if mark == X else X,
            winner=new_winner,
        )

    def glyph_row(self, row: int) -> str:
        a, b, c = (self.cells[row * 3 + i] for i in range(3))
        return f" {MARK_GLYPH[a]} | {MARK_GLYPH[b]} | {MARK_GLYPH[c]} "

    def render(self) -> str:
        sep = "---+---+---"
        return "\n".join(
            [
                self.glyph_row(0),
                sep,
                self.glyph_row(1),
                sep,
                self.glyph_row(2),
            ]
        )


def check_winner(cells: Sequence[int]) -> int | None:
    """Return 1 if X has won, 2 if O has won, 0 on a full-board draw,
    or None if the game is still in progress.

    Per tic-tac-toe rules the draw marker (0) is only valid when the
    board is full; a non-full board with no winner returns None.
    """
    if len(cells) != NUM_CELLS:
        raise ValueError(f"cells must have length {NUM_CELLS}, got {len(cells)}")
    for line in WIN_LINES:
        a, b, c = line
        if cells[a] != EMPTY and cells[a] == cells[b] == cells[c]:
            return cells[a]
    if all(cell != EMPTY for cell in cells):
        return DRAW
    return None


def available_moves(cells: Sequence[int]) -> list[int]:
    """Free-function form of ``Board.available_moves``."""
    if len(cells) != NUM_CELLS:
        raise ValueError(f"cells must have length {NUM_CELLS}, got {len(cells)}")
    return [i for i, c in enumerate(cells) if c == EMPTY]


def play(cells: Sequence[int], cell: int, mark: int) -> tuple[int, ...]:
    """Free-function form of ``Board.with_move``. Returns the new cells tuple.

    Caller is responsible for advancing ``to_move`` and computing the
    winner. (The service layer uses Board.with_move; this helper is for
    callers that only want the cells.)
    """
    if not (0 <= cell < NUM_CELLS):
        raise ValueError(f"cell must be in [0, {NUM_CELLS}), got {cell}")
    if mark not in (X, O):
        raise ValueError(f"mark must be X ({X}) or O ({O}), got {mark}")
    if cells[cell] != EMPTY:
        raise ValueError(f"cell {cell} is already occupied")
    new_cells = list(cells)
    new_cells[cell] = mark
    return tuple(new_cells)


# AI: minimax with alpha-beta pruning. Returns perfect-play move for the
# side whose turn it is.

_WIN_SCORE = 10
_DRAW_SCORE = 0
_LOSS_SCORE = -10


def _score_position(cells: Sequence[int], maximizing_for_x: bool) -> int:
    """Score a terminal position from X's POV. Non-terminal returns 0."""
    w = check_winner(cells)
    if w == X:
        return _WIN_SCORE
    if w == O:
        return _LOSS_SCORE
    return _DRAW_SCORE


def _minimax(
    cells: Sequence[int],
    to_move: int,
    alpha: int,
    beta: int,
) -> int:
    """Alpha-beta minimax. Returns the score of the position from X's POV
    (positive = good for X, negative = good for O) after both sides
    play optimally from here.

    ``to_move`` is the mark that plays next at this node.
    """
    w = check_winner(cells)
    if w is not None:
        return _score_position(cells, maximizing_for_x=True)

    moves = available_moves(cells)
    if to_move == X:
        best = -_WIN_SCORE - 1
        for m in moves:
            new_cells = play(cells, m, X)
            score = _minimax(new_cells, O, alpha, beta)
            if score > best:
                best = score
            if best > alpha:
                alpha = best
            if beta <= alpha:
                break
        return best

    best = _WIN_SCORE + 1
    for m in moves:
        new_cells = play(cells, m, O)
        score = _minimax(new_cells, X, alpha, beta)
        if score < best:
            best = score
        if best < beta:
            beta = best
        if beta <= alpha:
            break
    return best


def best_move(cells: Sequence[int], to_move: int = X) -> int:
    """Return the optimal move for ``to_move`` on ``cells``.

    On an empty board X plays a corner (standard perfect-play opening).
    With perfect play on both sides the game is always a draw.
    Raises ValueError if the game is already over or ``to_move`` is
    invalid.
    """
    if len(cells) != NUM_CELLS:
        raise ValueError(f"cells must have length {NUM_CELLS}, got {len(cells)}")
    if to_move not in (X, O):
        raise ValueError(f"to_move must be X ({X}) or O ({O}), got {to_move}")
    if check_winner(cells) is not None:
        raise ValueError("cannot request a move on a finished board")
    moves = available_moves(cells)
    if not moves:
        raise ValueError("no legal moves available")

    best_score: int | None = None
    best_cell: int | None = None
    for m in moves:
        new_cells = play(cells, m, to_move)
        # ``_minimax`` returns the score of the resulting position from
        # X's POV. For X-to-move we want the move that maximizes this;
        # for O-to-move we want the move that minimizes it (best for O).
        score = _minimax(new_cells, O if to_move == X else X, -_WIN_SCORE - 1, _WIN_SCORE + 1)
        if best_score is None:
            best_score = score
            best_cell = m
            continue
        if to_move == X and score > best_score or to_move == O and score < best_score:
            best_score = score
            best_cell = m
    assert best_cell is not None
    return best_cell


def suggest(cells: Sequence[int], to_move: int = X) -> dict[int, int]:
    """For each legal cell, return the score the position would have
    after playing there. Score is from the perspective of the side that
    just moved (so a positive number means the move is good for the
    mover). Useful for client-side hint UI.
    """
    if len(cells) != NUM_CELLS:
        raise ValueError(f"cells must have length {NUM_CELLS}, got {len(cells)}")
    out: dict[int, int] = {}
    for m in available_moves(cells):
        new_cells = play(cells, m, to_move)
        raw = _score_position(new_cells, maximizing_for_x=True)
        out[m] = raw if to_move == X else -raw
    return out


# Payout math. Win = bet*2 (1:1 winner-takes-bet), draw = bet (push),
# loss = 0. RAKE_PERCENT is reserved for v2.

def _apply_rake(payout: int) -> int:
    """Return ``payout`` with the house rake subtracted. RAKE_PERCENT
    is 0 in v1, so this is the identity function. When non-zero in v2,
    use integer ceiling math to avoid float drift.
    """
    if RAKE_PERCENT:
        return payout - -(-payout * RAKE_PERCENT // 100)
    return payout


def payout(winner: int | None, bet: int) -> int:
    """Return the amount credited to the player who placed the bet.

    ``winner`` is 1 (player X won), 2 (player O won), 0 (draw / push),
    or None. Caller passes the mark the bettor played as context:
    pass the bettor's mark to compute the credit for them. If the
    bettor won, they get bet*2; if it's a draw, bet; if they lost, 0.
    For "payout to the human bettor" calculations in mode 1 the human
    is always X, so caller passes the winning mark; for the bettor
    payout in mode 2 the caller must compute per-seat payouts and add
    them. This function is the single-source-of-truth math.
    """
    if bet < 0:
        raise ValueError(f"bet must be >= 0, got {bet}")
    if winner is None:
        return 0
    if winner == DRAW:
        return _apply_rake(bet)
    return _apply_rake(bet * 2)


def bettor_payout(winner: int | None, bettor_mark: int, bet: int) -> int:
    """Return the credit for a single bettor.

    ``winner`` is the winning mark (1, 2) or 0 for draw or None for
    mid-game. ``bettor_mark`` is the bettor's mark. If they match (or
    it's a draw), they get push-or-win payout; otherwise 0.
    """
    if winner is None:
        return 0
    if winner == DRAW:
        return _apply_rake(bet)
    if winner == bettor_mark:
        return _apply_rake(bet * 2)
    return 0


# Random fallback for the "RANDOMIZE_FIRST_MOVE" demo flag (off by default
# in v1; perfect vs perfect always draws).

RANDOMIZE_FIRST_MOVE = False


def maybe_random_first_move(cells: Sequence[int]) -> int:
    """If the board is empty and RANDOMIZE_FIRST_MOVE is on, return a
    random legal cell; otherwise return the perfect-play best_move."""
    import secrets
    if RANDOMIZE_FIRST_MOVE and all(c == EMPTY for c in cells):
        rng = secrets.SystemRandom()
        return rng.choice(available_moves(cells))
    return best_move(cells, X)
