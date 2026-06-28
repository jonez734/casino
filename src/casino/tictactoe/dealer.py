# casino/tictactoe/dealer.py
# Server-side AI opponent for tic-tac-toe.
#
# v1: hardcode perfect-play minimax (via lib.best_move). The Dealer
# class is a thin shim so the service can take a dealer via DI in
# tests and so that future difficulty knobs (easy/medium) can be
# added without touching service.py.

from __future__ import annotations

import secrets
from typing import Optional, Sequence, Union

from . import lib


def _default_rng() -> Union[secrets.SystemRandom, object]:
    return secrets.SystemRandom()


class TictactoeDealer:
    """AI opponent. Stateless beyond an optional RNG for future
    random-fallback difficulty modes.
    """

    def __init__(self, rng: Optional[Union[secrets.SystemRandom, object]] = None) -> None:
        self._rng = rng if rng is not None else _default_rng()

    def best_move(self, cells: Sequence[int], to_move: int) -> int:
        """Return the optimal move for ``to_move``."""
        return lib.best_move(cells, to_move)

    def random_legal_move(self, cells: Sequence[int]) -> int:
        """Return a uniformly random legal cell. Used for the
        RANDOMIZE_FIRST_MOVE demo flag (off by default in v1)."""
        moves = lib.available_moves(cells)
        if not moves:
            raise ValueError("no legal moves")
        return self._rng.choice(moves)
