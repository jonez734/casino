"""A settled round is shown as one block: each hand labelled with its own cards and result, and the round net.

The busted hand used to print beside the current hand as if it were the one being played. Each hand is now listed
in the round block with its own cards, and no finished hand is printed as the current hand.
"""

import argparse
from unittest.mock import patch

from casino.client import CasinoClient


def _render(state):
    import asyncio

    c = CasinoClient(argparse.Namespace(bed_host="127.0.0.1", bed_port=8765, bed_path="/"))
    c._loop = asyncio.new_event_loop()
    try:
        with patch("casino.client.casino_client.io.echo") as echo:
            asyncio.run(c.display_game_state(state))
    finally:
        c._loop.close()
    return [str(call.args[0]) for call in echo.call_args_list]


def test_a_settled_round_lists_each_hand_under_the_round_block():
    state = {
        "phase": "settled", "table_moniker": "blackjack-jam",
        "player_hand": ["5S", "6S", "6C"], "player_total": 17,
        "dealer_hand": ["10C", "4S", "9C"], "dealer_total": 23,
        "hands": [
            {"cards": ["8C", "4D", "10S"], "result": "bust", "net": -2},
            {"cards": ["5S", "6S", "6C"], "result": "win", "net": 1},
        ],
        "round_settled": {"net": -1, "dealer_total": 23, "outcomes": [
            {"player": "alice", "text": "you busted with 22, bet 2, net -2", "net": -2},
            {"player": "alice", "text": "dealer busted with 23, bet 1, net +1", "net": 1},
        ]},
        "available_actions": ["bet"],
    }
    lines = _render(state)
    assert any(l.startswith("Round") or "Round net" in l for l in lines)
    assert not any("Busted with" in l for l in lines), "a finished hand is not printed beside the current hand"


def test_the_current_open_hand_is_still_shown_as_your_hand():
    state = {
        "phase": "playing", "table_moniker": "blackjack-jam",
        "player_hand": ["5S", "6S"], "player_total": 11,
        "dealer_hand": ["10C", "hidden"], "dealer_total": 10,
        "hands": [{"cards": ["5S", "6S"], "result": None, "net": None}],
        "available_actions": ["hit", "stand"],
    }
    lines = _render(state)
    assert any("Your hand: 5S 6S" in l for l in lines)
