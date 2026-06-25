# casino/slots/lib.py
# Core data model for the slot machine.
#
# RTP definition
# --------------
#   RTP = E[payout] / bet
# where the expectation is taken over infinite spins at a flat bet of 1.
# The default paytable below is tuned for an RTP of approximately 0.92.
# Each table can override the target RTP via the SlotsConfig table config;
# out-of-band (0.80, 0.99) targets are rejected at config-validation time.

from __future__ import annotations

import secrets
import random as _random
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence, Union


DEFAULT_NUM_REELS = 5
DEFAULT_NUM_ROWS = 3
RTP_FLOOR = 0.80
RTP_CEIL = 0.99
RTP_DEFAULT = 0.92


@dataclass(frozen=True)
class Symbol:
    name: str
    weight: int
    glyph: str

    def __post_init__(self) -> None:
        if self.weight <= 0:
            raise ValueError(f"symbol {self.name!r} weight must be > 0, got {self.weight}")


# Default symbol set. Weights are tuned for the default paytable below.
DEFAULT_SYMBOLS: dict[str, Symbol] = {
    "CHERRY": Symbol("CHERRY", 8, "🍒"),
    "LEMON":  Symbol("LEMON",  7, "🍋"),
    "PLUM":   Symbol("PLUM",   6, "🟣"),
    "BELL":   Symbol("BELL",   5, "🔔"),
    "BAR":    Symbol("BAR",    4, "▮"),
    "SEVEN":  Symbol("SEVEN",  2, "7"),
    "BLANK":  Symbol("BLANK",  1, "·"),
}


# Default reel strips. Each reel is an independent list of symbols with its
# own weighting, so the symbol distribution is not perfectly uniform across
# the 5 reels. This is the standard "virtual reel" approach.
#
# Strips are tuned so that, combined with the default paytable, the
# realized RTP lands near 0.92. Per-reel stop counts are roughly
# proportional to DEFAULT_SYMBOLS weights, with a single BLANK stop per
# reel (so the blank ratio is about 3% per reel, not 33%). A
# BRUTE_FORCE_RTP_TEST in tests/test_slots_unit.py asserts the realized
# RTP is within +/- 0.02 of the 0.92 target over 10k spins.
DEFAULT_REELS: list[list[str]] = [
    # Reel 0 - heavy on high-pay symbols
    ["CHERRY", "CHERRY", "CHERRY", "CHERRY", "CHERRY", "CHERRY", "CHERRY", "CHERRY",
     "LEMON", "LEMON", "LEMON", "LEMON", "LEMON", "LEMON", "LEMON",
     "PLUM", "PLUM", "PLUM", "PLUM", "PLUM", "PLUM",
     "BELL", "BELL", "BELL", "BELL", "BELL",
     "BAR", "BAR", "BAR", "BAR",
     "SEVEN", "SEVEN",
     "BLANK"],
    # Reel 1
    ["CHERRY", "CHERRY", "CHERRY", "CHERRY", "CHERRY", "CHERRY", "CHERRY",
     "LEMON", "LEMON", "LEMON", "LEMON", "LEMON", "LEMON", "LEMON",
     "PLUM", "PLUM", "PLUM", "PLUM", "PLUM", "PLUM",
     "BELL", "BELL", "BELL", "BELL", "BELL",
     "BAR", "BAR", "BAR", "BAR",
     "SEVEN", "SEVEN",
     "BLANK"],
    # Reel 2 - middle reel, balanced
    ["CHERRY", "CHERRY", "CHERRY", "CHERRY", "CHERRY", "CHERRY", "CHERRY",
     "LEMON", "LEMON", "LEMON", "LEMON", "LEMON", "LEMON", "LEMON",
     "PLUM", "PLUM", "PLUM", "PLUM", "PLUM", "PLUM",
     "BELL", "BELL", "BELL", "BELL", "BELL",
     "BAR", "BAR", "BAR", "BAR",
     "SEVEN", "SEVEN",
     "BLANK"],
    # Reel 3
    ["CHERRY", "CHERRY", "CHERRY", "CHERRY", "CHERRY", "CHERRY", "CHERRY",
     "LEMON", "LEMON", "LEMON", "LEMON", "LEMON", "LEMON", "LEMON",
     "PLUM", "PLUM", "PLUM", "PLUM", "PLUM", "PLUM",
     "BELL", "BELL", "BELL", "BELL", "BELL",
     "BAR", "BAR", "BAR", "BAR",
     "SEVEN", "SEVEN",
     "BLANK"],
    # Reel 4
    ["CHERRY", "CHERRY", "CHERRY", "CHERRY", "CHERRY", "CHERRY", "CHERRY",
     "LEMON", "LEMON", "LEMON", "LEMON", "LEMON", "LEMON", "LEMON",
     "PLUM", "PLUM", "PLUM", "PLUM", "PLUM", "PLUM",
     "BELL", "BELL", "BELL", "BELL", "BELL",
     "BAR", "BAR", "BAR", "BAR",
     "SEVEN", "SEVEN",
     "BLANK"],
]


# Default paytable. Key: a tuple of symbol names forming a winning center-row
# combo. Value: multiplier applied to the bet.
#
# v1 evaluates only the center row. The single-BLANK entry is intentionally
# absent - blanks are non-paying symbols. Multipliers are scaled to land
# the realized RTP near 0.92 given the default reel strips above.
DEFAULT_PAYTABLE: dict[tuple[str, ...], int] = {
    ("SEVEN", "SEVEN", "SEVEN"):    145,
    ("BAR", "BAR", "BAR"):           45,
    ("BELL", "BELL", "BELL"):        32,
    ("PLUM", "PLUM", "PLUM"):        18,
    ("LEMON", "LEMON", "LEMON"):     14,
    ("CHERRY", "CHERRY", "CHERRY"):  10,
    ("SEVEN", "SEVEN"):               4,
    ("BAR", "BAR"):                   3,
    ("CHERRY",):                      1,
}


class RNG:
    """Cryptographic RNG helper. The default constructor uses
    ``secrets.SystemRandom``; tests can pass a seeded instance via
    ``RNG(random.Random(seed))`` for deterministic behavior.
    """

    def __init__(self, rand: Optional[Union[secrets.SystemRandom, _random.Random]] = None) -> None:
        self._rand = rand if rand is not None else secrets.SystemRandom()

    def weighted_choice(self, items: Sequence[Symbol]) -> Symbol:
        if not items:
            raise ValueError("weighted_choice requires at least one item")
        total = sum(s.weight for s in items)
        if total <= 0:
            raise ValueError("total weight must be positive")
        r = self._rand.random() * total
        cumulative = 0
        for s in items:
            cumulative += s.weight
            if r < cumulative:
                return s
        return items[-1]

    def choice_seq(self, items: Sequence[Symbol]) -> Symbol:
        """Pick one element of a sequence uniformly. Used for strip-based
        reels where each stop is a position on the virtual reel.
        """
        if not items:
            raise ValueError("choice_seq requires at least one item")
        idx = self._rand.randrange(len(items))
        return items[idx]

    def choice(self, items: Sequence[str]) -> str:
        if not items:
            raise ValueError("choice requires at least one item")
        return self._rand.choice(items)


class Reel:
    """A weighted reel that yields symbols on spin."""

    def __init__(
        self,
        stop_names: Sequence[str],
        symbols: dict[str, Symbol],
        rng: RNG,
    ) -> None:
        unknown = set(stop_names) - set(symbols.keys())
        if unknown:
            raise ValueError(f"reel references unknown symbols: {sorted(unknown)}")
        self._stops: list[Symbol] = [symbols[name] for name in stop_names]
        self._rng = rng
        self.symbols = symbols

    def spin(self) -> Symbol:
        return self._rng.choice_seq(self._stops)

    def as_strip(self) -> list[Symbol]:
        return list(self._stops)


@dataclass(frozen=True)
class Win:
    symbols: tuple[str, ...]
    multiplier: int
    payout: int

    def to_dict(self) -> dict:
        return {
            "symbols": list(self.symbols),
            "multiplier": self.multiplier,
            "payout": self.payout,
        }


@dataclass(frozen=True)
class SpinResult:
    reels: list[list[Symbol]]
    center_row: list[Symbol]
    wins: list[Win]
    bet: int
    payout: int
    net: int

    @property
    def did_win(self) -> bool:
        return self.payout > 0

    def to_dict(self) -> dict:
        return {
            "reels": [[s.name for s in col] for col in self.reels],
            "center_row": [s.name for s in self.center_row],
            "wins": [w.to_dict() for w in self.wins],
            "bet": self.bet,
            "payout": self.payout,
            "net": self.net,
        }


class Paytable:
    """Maps a winning symbol sequence to a bet multiplier."""

    def __init__(self, payouts: Optional[dict[tuple[str, ...], int]] = None) -> None:
        if payouts is None:
            self._payouts: dict[tuple[str, ...], int] = dict(DEFAULT_PAYTABLE)
        else:
            self._payouts = dict(payouts)
        self._validate()

    def _validate(self) -> None:
        for key, mult in self._payouts.items():
            if not isinstance(key, tuple) or not key:
                raise ValueError(f"paytable key must be a non-empty tuple, got {key!r}")
            if not all(isinstance(s, str) and s for s in key):
                raise ValueError(f"paytable key entries must be non-empty strings, got {key!r}")
            if not isinstance(mult, int) or mult < 0:
                raise ValueError(f"paytable multiplier must be a non-negative int, got {mult!r}")

    def get(self, key: tuple[str, ...]) -> Optional[int]:
        return self._payouts.get(key)

    def items(self) -> Iterable[tuple[tuple[str, ...], int]]:
        return self._payouts.items()

    def evaluate(self, center_row: Sequence[Symbol], bet: int) -> list[Win]:
        if bet <= 0:
            raise ValueError("bet must be positive")
        names = tuple(s.name for s in center_row)
        wins: list[Win] = []
        for key, mult in self._payouts.items():
            if mult <= 0:
                continue
            if self._matches(names, key):
                wins.append(Win(symbols=key, multiplier=mult, payout=bet * mult))
        return wins

    @staticmethod
    def _matches(row: tuple[str, ...], key: tuple[str, ...]) -> bool:
        if len(key) > len(row):
            return False
        return row[: len(key)] == key

    def theoretical_rtp(
        self,
        reels: Sequence[Reel],
        *,
        progress_every: int = 0,
        progress_total: int | None = None,
    ) -> float:
        """Exact theoretical RTP via per-paytable-key enumeration.

        For each paytable entry of length k, enumerate the first k reels
        over the *distinct symbol set* of the key, weighting each symbol
        by its strip-occurrence count in each reel. The remaining
        (num_reels - k) reels can be anything, so the count for that
        entry is multiplied by ``prod(strip_size for strip in reels[k:])``.
        This is exact and dramatically cheaper than full enumeration
        (~34.6M outcomes at default reel sizes).

        ``progress_every``: if > 0, calls
        ``bbsengine6.io.screen.updateprogress(done, total)`` every N
        entries. ``progress_total`` defaults to the sum of per-entry
        operation counts. The screen import is lazy; if the screen
        module is unavailable or uninitialized, progress is silently
        skipped and the RTP is still returned.

        Returns 0.0 if no reels are supplied.
        """
        if not reels:
            return 0.0

        stops = [r.as_strip() for r in reels]
        num_reels = len(reels)
        strip_sizes = [len(s) for s in stops]
        total_outcomes = 1
        for n in strip_sizes:
            total_outcomes *= n

        # Per-reel per-symbol strip occurrence count.
        symbol_counts_per_reel: list[dict[str, int]] = [
            {s.name: 0 for s in stop_list} for stop_list in stops
        ]
        for r_idx, stop_list in enumerate(stops):
            counts: dict[str, int] = {}
            for sym in stop_list:
                counts[sym.name] = counts.get(sym.name, 0) + 1
            symbol_counts_per_reel[r_idx] = counts

        screen_updateprogress = None
        if progress_every > 0:
            try:
                from bbsengine6.io import screen as _screen
                screen_updateprogress = _screen.updateprogress
            except Exception:
                screen_updateprogress = None

        running_total = 0
        running_count = 0
        progress_total_eff = progress_total
        if progress_total_eff is None and progress_every > 0:
            progress_total_eff = total_outcomes

        import itertools

        progress_threshold = progress_every
        next_progress = progress_threshold if progress_threshold > 0 else None

        for key, mult in self._payouts.items():
            if mult <= 0 or len(key) > num_reels:
                continue
            k = len(key)
            tail = 1
            for n in strip_sizes[k:]:
                tail *= n
            distinct_symbols = list(set(key))
            for combo in itertools.product(distinct_symbols, repeat=k):
                row = [Symbol(name, 1, name) for name in combo]
                wins = self.evaluate(row, bet=1)
                payout = sum(w.payout for w in wins)
                if payout <= 0:
                    continue
                # Per-reel occurrence count for this exact row.
                # Note: evaluate() matches row[:k] == key, so the first
                # k reels must equal the key (in order). The number of
                # ways to draw (key[0], key[1], ..., key[k-1]) from
                # the first k reels is the product of the per-reel
                # occurrence counts.
                ways = 1
                for r_idx, sym_name in enumerate(combo):
                    ways *= symbol_counts_per_reel[r_idx].get(sym_name, 0)
                if ways <= 0:
                    continue
                running_total += payout * ways * tail
                running_count += ways * tail
            if (
                next_progress is not None
                and screen_updateprogress is not None
                and running_count >= next_progress
            ):
                try:
                    screen_updateprogress(
                        running_count, progress_total_eff or total_outcomes
                    )
                except Exception:
                    screen_updateprogress = None
                next_progress = running_count + progress_threshold

        if progress_every > 0 and screen_updateprogress is not None:
            try:
                screen_updateprogress(
                    total_outcomes, progress_total_eff or total_outcomes
                )
            except Exception:
                pass

        return (running_total / total_outcomes) if total_outcomes else 0.0


def default_reels(symbols: dict[str, Symbol], rng: RNG) -> list[Reel]:
    return [Reel(stops, symbols, rng) for stops in DEFAULT_REELS]


def render_ascii(result: SpinResult) -> str:
    """Render a 5x3 grid with box-drawing characters. Center row is
    marked with an extra ``*`` on each side so players can see what
    was evaluated.
    """
    if not result.reels:
        return ""
    num_rows = max(len(col) for col in result.reels)
    cell_w = max(3, max(len(s.glyph) for col in result.reels for s in col))

    def cell(sym: Symbol) -> str:
        text = sym.glyph
        if len(text) < cell_w:
            text = text + " " * (cell_w - len(text))
        return text

    top = "┌" + "┬".join("─" * (cell_w + 2) for _ in result.reels) + "┐"
    mid = "├" + "┼".join("─" * (cell_w + 2) for _ in result.reels) + "┤"
    bot = "└" + "┴".join("─" * (cell_w + 2) for _ in result.reels) + "┘"

    lines = [top]
    for r in range(num_rows):
        row_parts: list[str] = []
        for col in result.reels:
            sym = col[r] if r < len(col) else Symbol("BLANK", 1, "·")
            text = " " + cell(sym) + " "
            if r == 1:
                text = f"*{cell(sym)}*"
            row_parts.append(text)
        lines.append("│" + "│".join(row_parts) + "│")
        if r < num_rows - 1:
            lines.append(mid)
    lines.append(bot)
    return "\n".join(lines)
