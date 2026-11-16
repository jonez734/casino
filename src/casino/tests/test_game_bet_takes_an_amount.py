"""``game bet 5`` places a bet of 5 without a prompt; a bare ``game bet`` still prompts for the amount.

Only ``bet`` takes an amount. The game parser accepts one optional amount after the subcommand, and the bet
command passes it on; with no amount the bet prompts as before.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from casino.commands.game import buildargs, lib


pytestmark = pytest.mark.unit


def test_the_parser_accepts_an_amount_after_bet():
    ns = buildargs(None).parse_args(["bet", "5"])
    assert ns.subcommand == "bet"
    assert ns.amount == 5


def test_the_parser_still_accepts_a_bare_bet():
    ns = buildargs(None).parse_args(["bet"])
    assert ns.subcommand == "bet"
    assert ns.amount is None


def _client():
    client = MagicMock()
    client.moniker = "jam"
    client.current_table_moniker = "blackjack-jam"
    client._loop = MagicMock()
    return client


def test_bet_with_an_amount_places_it_without_prompting():
    client = _client()
    with patch.object(lib, "_check_access", return_value=True):
        lib.bet(SimpleNamespace(), client=client, amount=5)
    client.cmd_bet.assert_called_once_with(amount=5)


def test_bare_bet_still_prompts():
    client = _client()
    with patch.object(lib, "_check_access", return_value=True):
        lib.bet(SimpleNamespace(), client=client, amount=None)
    client.cmd_bet.assert_called_once_with(amount=None)
