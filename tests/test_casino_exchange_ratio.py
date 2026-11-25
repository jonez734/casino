"""Casino's credits <-> coins exchange passes each player's own (num, den) ratio to bbsengine6 BankService.exchange.

The ratio is two positive integers per player (ratio_num, ratio_den), defaulting to 1:1 (the old 1.00).
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from casino import bankratio


def test_the_default_ratio_is_one_to_one():
    assert bankratio.DEFAULT_RATIO == (1, 1)


def test_ratio_for_reads_the_players_two_integer_columns():
    row = {"ratio_num": 5, "ratio_den": 4}
    assert bankratio.ratio_for_row(row) == (5, 4)


@pytest.mark.parametrize("row", [{"ratio_num": 0, "ratio_den": 1}, {"ratio_num": 1, "ratio_den": -2},
                                  {"ratio_num": None, "ratio_den": None}])
def test_an_invalid_stored_ratio_falls_back_to_one_to_one(row):
    assert bankratio.ratio_for_row(row) == (1, 1)


def test_exchange_passes_the_players_ratio_to_bbsengine6():
    bank = MagicMock()
    bank.exchange.return_value = {"success": True}
    bankratio.exchange_for_player(bank, "jam", 4, to="tokens", token_moniker="jam_credits", ratio=(5, 4))
    bank.exchange.assert_called_once_with("jam", 4, to="tokens", ratio=(5, 4), token_moniker="jam_credits")
