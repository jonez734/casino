# casino/tests/test_yahtzee_lib.py
# Tests for yahtzee/lib.py: scoring, rake math, suggestions, totals.

import pytest

from casino.yahtzee import lib


class TestScoring:
    def test_yahtzee_50(self):
        assert lib.score((5, 5, 5, 5, 5), "yahtzee") == 50

    def test_yahtzee_zero_when_not_all_same(self):
        assert lib.score((5, 5, 5, 5, 4), "yahtzee") == 0

    def test_full_house_25(self):
        assert lib.score((3, 3, 5, 5, 5), "full_house") == 25

    def test_full_house_zero_when_not_full_house(self):
        assert lib.score((3, 3, 3, 5, 6), "full_house") == 0

    def test_small_straight_30(self):
        # 1-2-3-4 + filler
        assert lib.score((1, 2, 3, 4, 6), "small_straight") == 30

    def test_small_straight_zero_when_no_run(self):
        assert lib.score((1, 1, 1, 1, 1), "small_straight") == 0

    def test_large_straight_40(self):
        assert lib.score((1, 2, 3, 4, 5), "large_straight") == 40
        assert lib.score((2, 3, 4, 5, 6), "large_straight") == 40

    def test_large_straight_zero_when_only_small(self):
        assert lib.score((1, 2, 3, 4, 6), "large_straight") == 0

    def test_three_of_a_kind_sums_dice(self):
        assert lib.score((4, 4, 4, 2, 6), "three_of_a_kind") == 20

    def test_three_of_a_kind_zero_when_no_triple(self):
        assert lib.score((4, 4, 5, 2, 6), "three_of_a_kind") == 0

    def test_four_of_a_kind_sums_dice(self):
        assert lib.score((4, 4, 4, 4, 6), "four_of_a_kind") == 22

    def test_chance_sums_dice(self):
        assert lib.score((1, 2, 3, 4, 5), "chance") == 15

    def test_ones(self):
        assert lib.score((1, 1, 3, 4, 5), "ones") == 2

    def test_sixes(self):
        assert lib.score((6, 6, 3, 4, 5), "sixes") == 12

    def test_upper_sums_zero_when_no_match(self):
        assert lib.score((2, 3, 4, 5, 6), "ones") == 0

    def test_unknown_category_raises(self):
        with pytest.raises(ValueError):
            lib.score((1, 2, 3, 4, 5), "bogus")

    def test_wrong_dice_length_raises(self):
        with pytest.raises(ValueError):
            lib.score((1, 2, 3), "ones")


class TestRakeDisabled:
    def test_rake_percent_is_zero(self):
        assert lib.RAKE_PERCENT == 0

    def test_net_payout_equals_score(self):
        assert lib.net_payout(50) == 50
        assert lib.net_payout(25) == 25
        assert lib.net_payout(0) == 0
        assert lib.net_payout(1) == 1
        assert lib.net_payout(100) == 100

    def test_apply_rake_is_identity(self):
        for s in (0, 1, 7, 25, 40, 50, 100, 250):
            assert lib._apply_rake(s) == s


class TestCategories:
    def test_categories_count(self):
        assert len(lib.CATEGORIES) == 13

    def test_categories_order(self):
        assert lib.CATEGORIES == (
            "ones", "twos", "threes", "fours", "fives", "sixes",
            "three_of_a_kind", "four_of_a_kind", "full_house",
            "small_straight", "large_straight", "yahtzee", "chance",
        )

    def test_upper_count(self):
        assert len(lib.UPPER_CATEGORIES) == 6

    def test_lower_count(self):
        assert len(lib.LOWER_CATEGORIES) == 7


class TestSuggest:
    def test_suggest_for_yahtzee_dice(self):
        s = lib.suggest((1, 1, 1, 1, 1))
        assert s["yahtzee"] == 50
        assert s["chance"] == 5
        assert s["three_of_a_kind"] == 5
        assert s["four_of_a_kind"] == 5
        assert s["ones"] == 5
        assert s["twos"] == 0
        assert s["sixes"] == 0
        # 1,1,1,1,1 is a yahtzee but NOT a full house (full house needs [2,3])
        assert s["full_house"] == 0

    def test_suggest_returns_all_categories(self):
        s = lib.suggest((1, 2, 3, 4, 5))
        assert set(s.keys()) == set(lib.CATEGORIES)


class TestTotals:
    def test_upper_total_with_some_unfilled(self):
        sc = {"ones": 3, "twos": None, "threes": 6, "fours": 8, "fives": 15, "sixes": None}
        assert lib.upper_total(sc) == 32

    def test_upper_total_all_filled(self):
        sc = {c: 5 for c in lib.UPPER_CATEGORIES}
        assert lib.upper_total(sc) == 30

    def test_lower_total(self):
        sc = {**{c: None for c in lib.UPPER_CATEGORIES},
              "three_of_a_kind": 18, "four_of_a_kind": 0,
              "full_house": 25, "small_straight": 30,
              "large_straight": 0, "yahtzee": 0, "chance": 22}
        assert lib.lower_total(sc) == 95

    def test_grand_total_no_bonus_in_v1(self):
        # v1 has no upper-section bonus; total is just upper + lower
        sc = {c: 5 for c in lib.CATEGORIES}
        assert lib.grand_total(sc) == sum(sc.values())
