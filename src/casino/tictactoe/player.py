# casino/tictactoe/player.py
# Input validation for human tic-tac-toe moves.
#
# BED-mode is the primary surface in v1, but the rules engine should
# not depend on the WS layer, so this thin adapter is the canonical
# "is this move from a human legal at this turn" check. The service
# layer calls validate_move and translates None / error-string into
# the BED error code.

from __future__ import annotations

from typing import Optional, Sequence


class TictactoePlayer:
    """Lightweight per-seat validation shim.

    v1 is BED-only and the service does the heavy lifting; this class
    is a thin input adapter and a place to hang per-player state in
    future v2 work (stats, hot-seat preferences, etc.).
    """

    def __init__(self, moniker: str, mark: int) -> None:
        if mark not in (1, 2):
            raise ValueError(f"mark must be 1 (X) or 2 (O), got {mark}")
        self.moniker = moniker
        self.mark = mark

    def validate_move(self, cell: object, cells: Sequence[int]) -> Optional[str]:
        """Return None if the move is legal, else a human-readable error.

        Does NOT check whose turn it is (the service layer enforces
        that against game.turn_moniker). Does check:

        - ``cell`` is an int
        - ``cell`` is in [0, 9)
        - the cell is currently empty
        - the game is not already over
        """
        if not isinstance(cell, int) or isinstance(cell, bool):
            return "cell must be an integer in [0, 8]"
        if not (0 <= cell < 9):
            return f"cell must be in [0, 8], got {cell}"
        if len(cells) != 9:
            return "internal: cells must have length 9"
        if cells[cell] != 0:
            return f"cell {cell} is already occupied"
        return None
