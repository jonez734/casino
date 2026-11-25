"""CasinoBankService.exchange: casino uses a fixed 1:1 rate and refuses non-positive amounts.

Mirrors empyre's EmpyreBankService. The rate is not per player: every exchange passes (1, 1) to
bbsengine6's BankService.exchange, and a non-positive or non-integer amount never reaches the ledger.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from casino.services.bank import CasinoBankService, CASINO_EXCHANGE_RATIO


def test_the_casino_rate_is_a_fixed_one_to_one():
    assert CASINO_EXCHANGE_RATIO == (1, 1)


def test_exchange_passes_the_fixed_rate_to_bbsengine6():
    with patch("casino.services.bank.BankModule") as cls:
        cls.return_value.exchange.return_value = {"success": True}
        svc = CasinoBankService(SimpleNamespace(debug=False))
        svc.exchange("jam", 4, to="tokens", token_moniker="jam_credits")
    cls.return_value.exchange.assert_called_once_with(
        "jam", 4, to="tokens", ratio=(1, 1), token_moniker="jam_credits"
    )


@pytest.mark.parametrize("amount", [0, -1, 2.5, True, "4"])
def test_a_non_positive_or_non_integer_amount_is_refused_before_the_ledger(amount):
    with patch("casino.services.bank.BankModule") as cls:
        svc = CasinoBankService(SimpleNamespace(debug=False))
        result = svc.exchange("jam", amount, to="tokens", token_moniker="jam_credits")
    assert result["success"] is False
    cls.return_value.exchange.assert_not_called()
