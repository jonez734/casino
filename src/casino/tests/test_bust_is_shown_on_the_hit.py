"""A player's bust is shown on the table as soon as it happens, not only when they try another action.

The state after a hit carries the hand's status. A busted hand must print a clear line that the hand is over and
what it lost, so the player is not left guessing until 'game stand' is refused.
"""

import argparse
import asyncio
from unittest.mock import patch

import pytest

from casino.client import CasinoClient


pytestmark = pytest.mark.unit


def _client():
    c = CasinoClient(argparse.Namespace(bed_host="127.0.0.1", bed_port=8765, bed_path="/"))
    c._loop = asyncio.new_event_loop()
    return c


def test_a_busted_hand_is_announced_on_the_table():
    client = _client()
    state = {
        "phase": "playing",
        "player_hand": ["10S", "5D", "JD"],
        "player_total": 25,
        "dealer_hand": ["QC", "hidden"],
        "dealer_total": 10,
        "hands": [{"cards": ["10S", "5D", "JD"], "status": "bust", "total": 25, "bet": 10,
                   "result": "bust", "net": -10}],
        "available_actions": [],
    }
    with patch("casino.client.casino_client.io.echo") as echo:
        asyncio.run(client.display_game_state(state))
    printed = " ".join(str(c.args[0]) for c in echo.call_args_list)
    assert "busted" in printed.lower()
    assert "-10" in printed
    client._loop.close()
