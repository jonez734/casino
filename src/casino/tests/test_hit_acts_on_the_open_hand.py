"""A hit (or stand, double, split, surrender) acts on the player's open hand, not a finished one.

A player can hold several hands in one game (one per bet). get_player_hand returned an arbitrary one with no
order and no status filter, so a hit could draw onto a hand that had already busted or stood, and the cards on
screen stopped changing. The action now picks the open hand; a hand that is finished is never acted on.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from casino.dal import game as dal_game
from casino.services import game as game_mod


pytestmark = pytest.mark.unit


def test_the_open_hand_is_chosen_over_a_finished_one():
    hands = [
        {"id": 322, "playermoniker": "jam", "cards": ["QS", "4S", "KS", "5S"], "attrs": {"status": "bust"}},
        {"id": 323, "playermoniker": "jam", "cards": ["10H", "JH"], "attrs": {}},
    ]
    with patch.object(dal_game, "get_player_hands", return_value=hands):
        chosen = game_mod.GameService._open_hand(SimpleNamespace(args=None, _pool=None), 162, "jam")
    assert chosen["id"] == 323


def test_no_open_hand_means_none():
    hands = [{"id": 322, "playermoniker": "jam", "cards": [], "attrs": {"status": "bust"}}]
    with patch.object(dal_game, "get_player_hands", return_value=hands):
        assert game_mod.GameService._open_hand(SimpleNamespace(args=None, _pool=None), 162, "jam") is None
