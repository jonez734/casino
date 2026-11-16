"""A typed ``game bet 10`` reaches the bet with 10; a bare ``game bet`` prompts for it.

The menu parses the amount into the choice's args, but the game dispatch dropped the args and always prompted.
"""

import argparse
import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from casino.client import CasinoClient


pytestmark = pytest.mark.unit


@pytest.fixture
def client():
    c = CasinoClient(argparse.Namespace(bed_host="127.0.0.1", bed_port=8765, bed_path="/"))
    c.current_table_game_type = "blackjack"
    c._loop = asyncio.new_event_loop()
    yield c
    c._loop.close()


def test_a_typed_amount_is_passed_to_the_bet(client):
    with patch.object(client, "cmd_bet") as cmd_bet:
        client._dispatch_game("bet", SimpleNamespace(amount=10))
    cmd_bet.assert_called_once_with(amount=10)


def test_a_bare_bet_passes_no_amount_so_it_prompts(client):
    with patch.object(client, "cmd_bet") as cmd_bet:
        client._dispatch_game("bet", SimpleNamespace(amount=None))
    cmd_bet.assert_called_once_with(amount=None)


def test_dispatch_with_no_args_still_works(client):
    with patch.object(client, "cmd_bet") as cmd_bet:
        client._dispatch_game("bet", None)
    cmd_bet.assert_called_once_with(amount=None)
