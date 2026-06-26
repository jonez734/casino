# casino/yahtzee/dealer.py
# Server-side dice + lock state for yahtzee.
# No DB, no I/O, no BED. Used by service.py and the test suite.

from __future__ import annotations

import random
import secrets
from typing import Optional, Sequence, Union


def _default_rng() -> Union[secrets.SystemRandom, random.Random]:
    return secrets.SystemRandom()


class YahtzeeDealer:
    """Roll 5 dice in [1,6], preserve locked indices across rolls.

    State is the per-round dice tuple and lock mask; this class is
    stateless beyond holding a single round. A ``YahtzeeGame``
    (service.py) holds the multi-round state and calls into this
    dealer for individual rolls.
    """

    def __init__(self, rng: Optional[Union[secrets.SystemRandom, random.Random]] = None) -> None:
        self._rng = rng if rng is not None else _default_rng()

    def roll_dice(self, n: int) -> tuple[int, ...]:
        """Roll ``n`` fresh dice in [1,6]."""
        if n < 0:
            raise ValueError(f"n must be >= 0, got {n}")
        return tuple(self._rng.randint(1, 6) for _ in range(n))

    def reroll(
        self,
        dice: Sequence[int],
        locked: Sequence[bool],
    ) -> tuple[int, ...]:
        """Return a new 5-tuple: locked indices keep their value, unlocked are re-rolled."""
        if len(dice) != 5 or len(locked) != 5:
            raise ValueError("dice and locked must each have length 5")
        new_dice: list[int] = []
        for i in range(5):
            if locked[i]:
                new_dice.append(int(dice[i]))
            else:
                new_dice.append(self._rng.randint(1, 6))
        return tuple(new_dice)

    def fresh(self) -> tuple[int, ...]:
        """Return a fresh 5-tuple of dice."""
        return self.roll_dice(5)
