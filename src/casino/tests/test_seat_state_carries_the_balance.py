"""A player's own game state carries their current balance, and the client's header follows it.

The header kept the login balance after a bet: the server debited the stake, but nothing sent the new balance to the
client. A seat's own state now carries its balance, and the client takes it from there.
"""

import argparse
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from casino.api.payloads import GameState
from casino.client import CasinoClient
from casino.services import game as game_mod


pytestmark = pytest.mark.unit


def test_a_players_state_includes_their_balance():
    svc = game_mod.GameService.__new__(game_mod.GameService)
    svc.args = SimpleNamespace()
    svc._pool = None
    with patch.object(game_mod.dal_table, "get_table", return_value={"attrs": {}}), \
         patch.object(game_mod.dal_game, "get_current_game", return_value=None), \
         patch.object(game_mod.dal_table, "seated_monikers", return_value=[]), \
         patch.object(game_mod.dal_player, "get_player_balance", return_value=90):
        state = svc.get_game_state("blackjack-jam", "alice").to_dict()
    assert state["balance"] == 90


def test_the_client_header_follows_the_state_balance():
    client = CasinoClient(argparse.Namespace(bed_host="127.0.0.1", bed_port=8765, bed_path="/"))
    client.balance = 100
    client._loop = __import__("asyncio").new_event_loop()
    try:
        client._apply_game_state_balance({"balance": 90})
    finally:
        client._loop.close()
    assert client.balance == 90
