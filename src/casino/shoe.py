# casino/shoe.py
# The shared card shoe. Every card game draws from a shoe, even when it holds one deck.
#
# Cards are strings in the casino format: pips plus a one-letter suit (``AH``, ``10S``, ``KD``).
# A shoe holds ``decks`` full 52-card decks, shuffled together. It is reshuffled (rebuilt and
# shuffled) once the number of cards drawn passes ``threshold`` of the shoe size, so a hand is
# never dealt from a shoe that is nearly empty.
#
# This class is in-memory and pure. Games that persist a shoe (blackjack keeps its shoe in the
# table row) read and write ``cards`` and ``uses`` themselves.

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional

SUITS = ("H", "D", "S", "C")
PIPS = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K")

DEFAULT_DECKS = 1
DEFAULT_THRESHOLD = 0.8


def build_cards(decks: int) -> list[str]:
    """A fresh, unshuffled shoe of ``decks`` standard decks."""
    if decks < 1:
        raise ValueError("a shoe needs at least one deck")
    return [pips + suit for _ in range(decks) for suit in SUITS for pips in PIPS]


@dataclass
class Shoe:
    """A shuffled shoe of cards that reshuffles at a threshold."""

    decks: int = DEFAULT_DECKS
    threshold: float = DEFAULT_THRESHOLD
    cards: list[str] = field(default_factory=list)
    uses: int = 0
    reshuffles: int = 0
    _rng: Optional[random.Random] = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not 0 < self.threshold <= 1:
            raise ValueError("threshold must be in (0, 1]")
        if not self.cards:
            self._rebuild()

    @property
    def size(self) -> int:
        return self.decks * len(SUITS) * len(PIPS)

    @property
    def remaining(self) -> int:
        return len(self.cards)

    def _shuffle(self) -> None:
        (self._rng or random).shuffle(self.cards)

    def _rebuild(self) -> None:
        self.cards = build_cards(self.decks)
        self._shuffle()
        self.uses = 0
        self.reshuffles += 1

    def needs_reshuffle(self) -> bool:
        """True once more than ``threshold`` of the shoe has been drawn."""
        return self.uses > self.size * self.threshold

    def draw(self) -> str:
        """Draw the next card, reshuffling a fresh shoe first when the threshold is passed."""
        if self.needs_reshuffle() or not self.cards:
            self._rebuild()
        card = self.cards.pop()
        self.uses += 1
        return card

    def burn(self) -> str:
        """Discard one card face down (a burn card). Counts toward the threshold."""
        return self.draw()

    def draw_many(self, count: int) -> list[str]:
        return [self.draw() for _ in range(count)]

    def seed(self, rng: random.Random) -> None:
        """Use a specific random source (tests and reproducible deals)."""
        self._rng = rng

    @classmethod
    def from_state(
        cls, cards: list[str], uses: int, *, decks: int, threshold: float = DEFAULT_THRESHOLD
    ) -> "Shoe":
        """Restore a shoe from saved state (the cards still in it and the draws so far).

        Used by games that persist their shoe. The restored shoe does not reshuffle until the
        threshold is passed, exactly as the live shoe would.
        """
        shoe = cls(decks=decks, threshold=threshold, cards=list(cards))
        shoe.uses = uses
        return shoe
