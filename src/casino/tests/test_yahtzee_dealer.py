# casino/tests/test_yahtzee_dealer.py
# Tests for yahtzee/dealer.py: dice rolls, lock preservation, RNG.

import random
import pytest

from casino.yahtzee.dealer import YahtzeeDealer


class TestRoll:
    def test_roll_dice_returns_n_ints(self):
        d = YahtzeeDealer(rng=random.Random(42))
        result = d.roll_dice(5)
        assert len(result) == 5
        assert all(isinstance(x, int) for x in result)

    def test_roll_dice_in_range(self):
        d = YahtzeeDealer(rng=random.Random(1))
        for _ in range(100):
            n = d.roll_dice(5)
            for x in n:
                assert 1 <= x <= 6

    def test_roll_dice_n_zero(self):
        d = YahtzeeDealer(rng=random.Random(0))
        assert d.roll_dice(0) == ()

    def test_roll_dice_n_negative_raises(self):
        d = YahtzeeDealer(rng=random.Random(0))
        with pytest.raises(ValueError):
            d.roll_dice(-1)

    def test_fresh_returns_5_dice(self):
        d = YahtzeeDealer(rng=random.Random(7))
        result = d.fresh()
        assert len(result) == 5
        for x in result:
            assert 1 <= x <= 6

    def test_seeded_rng_is_deterministic(self):
        a = YahtzeeDealer(rng=random.Random(42))
        b = YahtzeeDealer(rng=random.Random(42))
        assert a.fresh() == b.fresh()

    def test_different_seeds_diverge(self):
        a = YahtzeeDealer(rng=random.Random(1))
        b = YahtzeeDealer(rng=random.Random(999))
        assert a.fresh() != b.fresh()


class TestLocks:
    def test_reroll_with_all_locked_unchanged(self):
        d = YahtzeeDealer(rng=random.Random(0))
        dice = (1, 2, 3, 4, 5)
        locked = (True, True, True, True, True)
        assert d.reroll(dice, locked) == dice

    def test_reroll_with_none_locked_rolls_fresh(self):
        d = YahtzeeDealer(rng=random.Random(0))
        dice = (1, 2, 3, 4, 5)
        locked = (False, False, False, False, False)
        new_dice = d.reroll(dice, locked)
        # All positions replaced
        for old, new in zip(dice, new_dice):
            assert 1 <= new <= 6
        # With a fresh seed and 5 unlocks, the result is not the original tuple
        # in general, but this is not guaranteed; we only assert range.
        assert len(new_dice) == 5

    def test_reroll_preserves_locked_indices(self):
        d = YahtzeeDealer(rng=random.Random(0))
        dice = (1, 2, 3, 4, 5)
        locked = (True, False, True, False, True)
        new_dice = d.reroll(dice, locked)
        # Locked indices keep their original value
        assert new_dice[0] == 1
        assert new_dice[2] == 3
        assert new_dice[4] == 5
        # Unlocked indices are in range
        assert 1 <= new_dice[1] <= 6
        assert 1 <= new_dice[3] <= 6

    def test_reroll_wrong_dice_length_raises(self):
        d = YahtzeeDealer(rng=random.Random(0))
        with pytest.raises(ValueError):
            d.reroll((1, 2, 3), (True, True, True, True, True))

    def test_reroll_wrong_locked_length_raises(self):
        d = YahtzeeDealer(rng=random.Random(0))
        with pytest.raises(ValueError):
            d.reroll((1, 2, 3, 4, 5), (True, False, True))


class TestMaxRollsSequence:
    """Simulate a full 3-roll round and assert dice evolve sensibly."""

    def test_three_rolls_evolve(self):
        d = YahtzeeDealer(rng=random.Random(123))
        dice = d.fresh()  # roll 1
        assert len(dice) == 5
        # roll 2: keep all
        dice = d.reroll(dice, (True, True, True, True, True))
        assert len(dice) == 5
        # roll 3: keep all
        dice = d.reroll(dice, (True, True, True, True, True))
        assert len(dice) == 5
        # After "exhausting" rolls the dice are stable
        frozen = dice
        dice = d.reroll(dice, (True, True, True, True, True))
        assert dice == frozen
