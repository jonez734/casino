# casino/slots/dealer.py
# Single-player slot dealer: spin + evaluate in one call.

from __future__ import annotations

from typing import Optional, Sequence

from .lib import (
    DEFAULT_NUM_ROWS,
    Paytable,
    Reel,
    RNG,
    SpinResult,
    Symbol,
)


class SlotDealer:
    """Owns the reels, the paytable, and the RNG for a single slot table.

    A dealer is bound to one table's configuration at construction time.
    Multiple tables get multiple dealers.
    """

    def __init__(
        self,
        reels: Sequence[Reel],
        paytable: Paytable,
        rng: Optional[RNG] = None,
    ) -> None:
        if not reels:
            raise ValueError("SlotDealer requires at least one reel")
        self._reels: list[Reel] = list(reels)
        self._paytable: Paytable = paytable
        self._rng: RNG = rng or RNG()

    @property
    def num_reels(self) -> int:
        return len(self._reels)

    @property
    def num_rows(self) -> int:
        return DEFAULT_NUM_ROWS

    @property
    def paytable(self) -> Paytable:
        return self._paytable

    def spin_grid(self) -> list[list[Symbol]]:
        """Spin all reels and return a num_reels x num_rows grid."""
        return [[r.spin() for _ in range(self.num_rows)] for r in self._reels]

    @staticmethod
    def center_row(grid: Sequence[Sequence[Symbol]]) -> list[Symbol]:
        if not grid:
            raise ValueError("grid is empty")
        rows_per_col = {len(col) for col in grid}
        if len(rows_per_col) != 1:
            raise ValueError(f"inconsistent row counts: {rows_per_col}")
        n_rows = rows_per_col.pop()
        if n_rows == 0:
            raise ValueError("grid has no rows")
        mid = n_rows // 2
        return [col[mid] for col in grid]

    def evaluate(self, grid: Sequence[Sequence[Symbol]], bet: int) -> SpinResult:
        if bet <= 0:
            raise ValueError(f"bet must be positive, got {bet}")
        center = self.center_row(grid)
        wins = self._paytable.evaluate(center, bet=bet)
        payout = sum(w.payout for w in wins)
        return SpinResult(
            reels=[list(col) for col in grid],
            center_row=center,
            wins=wins,
            bet=bet,
            payout=payout,
            net=payout - bet,
        )

    def play(self, bet: int) -> SpinResult:
        if bet <= 0:
            raise ValueError(f"bet must be positive, got {bet}")
        return self.evaluate(self.spin_grid(), bet)
