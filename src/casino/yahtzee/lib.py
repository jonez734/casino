# casino/yahtzee/lib.py
# Pure engine for yahtzee: constants, scoring, rake math, suggestions.
# No DB, no I/O, no BED. Used by service.py and the test suite.

from __future__ import annotations

from collections import Counter
from typing import Sequence


NUM_DICE = 5
NUM_ROLLS = 3
MIN_BET = 10
MAX_BET = 1000

# TODO(yahtzee-v2-multiplayer): Re-enable rake when yahtzee goes multiplayer.
# In v1 the player is paid the full score; no house cut.
RAKE_PERCENT = 0  # 0.05 in v2; net_payout returns score - ceil(score * 0.05)

CATEGORIES: tuple[str, ...] = (
    "ones",
    "twos",
    "threes",
    "fours",
    "fives",
    "sixes",
    "three_of_a_kind",
    "four_of_a_kind",
    "full_house",
    "small_straight",
    "large_straight",
    "yahtzee",
    "chance",
)

UPPER_CATEGORIES: tuple[str, ...] = (
    "ones", "twos", "threes", "fours", "fives", "sixes",
)

LOWER_CATEGORIES: tuple[str, ...] = (
    "three_of_a_kind", "four_of_a_kind", "full_house",
    "small_straight", "large_straight", "yahtzee", "chance",
)

FIXED_SCORES: dict[str, int] = {
    "full_house": 25,
    "small_straight": 30,
    "large_straight": 40,
    "yahtzee": 50,
}


def _apply_rake(score: int) -> int:
    """RAKE_DISABLED: returns score unchanged. In v2 returns score - rake."""
    # if RAKE_PERCENT:
    #     return score - (score * RAKE_PERCENT.numerator // RAKE_PERCENT.denominator)
    return score


def net_payout(score: int) -> int:
    """The amount credited to the player on a successful score. In v1, equals score."""
    return _apply_rake(score)


def _dice_total(dice: Sequence[int]) -> int:
    return sum(dice)


def _is_yahtzee(dice: Sequence[int]) -> bool:
    return len(set(dice)) == 1


def _is_full_house(dice: Sequence[int]) -> bool:
    counts = sorted(Counter(dice).values())
    return counts == [2, 3]


def _has_n_of_a_kind(dice: Sequence[int], n: int) -> bool:
    return any(c >= n for c in Counter(dice).values())


def _small_straight_high(dice: Sequence[int]) -> int:
    """Return the highest 4-run present, or 0 if none.

    Standard yahtzee small_straight is 4 consecutive dice. Valid
    high-ends are 4, 5, 6.
    """
    unique = set(dice)
    for high in (6, 5, 4):
        needed = {high, high - 1, high - 2, high - 3}
        if needed.issubset(unique):
            return high
    return 0


def _large_straight(dice: Sequence[int]) -> bool:
    unique = set(dice)
    return unique == {1, 2, 3, 4, 5} or unique == {2, 3, 4, 5, 6}


def score(dice: Sequence[int], category: str) -> int:
    """Compute the score for ``dice`` in ``category``.

    Standard yahtzee values. ``category`` must be one of the 13
    categories; raises ``ValueError`` otherwise. The category is
    not checked for "already used" here; that is the caller's
    responsibility (typically ``YahtzeeGame.score``).
    """
    if category not in CATEGORIES:
        raise ValueError(f"unknown category: {category!r}")
    if len(dice) != NUM_DICE:
        raise ValueError(f"dice must be a sequence of {NUM_DICE}, got {len(dice)}")

    if category in FIXED_SCORES:
        if category == "yahtzee" and not _is_yahtzee(dice):
            return 0
        if category == "full_house" and not _is_full_house(dice):
            return 0
        if category == "large_straight" and not _large_straight(dice):
            return 0
        if category == "small_straight" and _small_straight_high(dice) == 0:
            return 0
        return FIXED_SCORES[category]

    if category == "three_of_a_kind":
        return _dice_total(dice) if _has_n_of_a_kind(dice, 3) else 0
    if category == "four_of_a_kind":
        return _dice_total(dice) if _has_n_of_a_kind(dice, 4) else 0
    if category == "chance":
        return _dice_total(dice)

    # Upper section: sum of the face value times count.
    face = CATEGORIES.index(category) + 1
    return face * sum(1 for d in dice if d == face)


def suggest(dice: Sequence[int]) -> dict[str, int]:
    """Best possible score for every category given the current dice.

    Used by clients to render a "what would I get if I scored here"
    preview. All 13 categories are returned; categories that do
    not match return 0 (which is the standard yahtzee "open
    category" zero-score behavior).
    """
    if len(dice) != NUM_DICE:
        raise ValueError(f"dice must be a sequence of {NUM_DICE}, got {len(dice)}")
    return {c: score(dice, c) for c in CATEGORIES}


def upper_total(scorecard: dict[str, int | None]) -> int:
    return sum(scorecard.get(c) or 0 for c in UPPER_CATEGORIES)


def lower_total(scorecard: dict[str, int | None]) -> int:
    return sum(scorecard.get(c) or 0 for c in LOWER_CATEGORIES)


def grand_total(scorecard: dict[str, int | None]) -> int:
    """v1: no upper-section bonus. Sum upper + lower only."""
    return upper_total(scorecard) + lower_total(scorecard)
