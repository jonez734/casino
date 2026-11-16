"""A game-state read reports a missing balance as None; it never fails the state (and so never blocks a join or a seat).

The balance shown in the state is informational. A member with no recorded credits must still be able to sit down and
see the table. The explicit error belongs to a bet, which needs the money, not to a read of the state.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from casino.dal import player as dal_player
from casino.services import game as game_mod


pytestmark = pytest.mark.unit


def test_a_state_read_with_missing_credits_still_returns_the_state():
    svc = game_mod.GameService.__new__(game_mod.GameService)
    svc.args = SimpleNamespace()
    svc._pool = None
    with patch.object(game_mod.dal_table, "get_table", return_value={"attrs": {}}), \
         patch.object(game_mod.dal_game, "get_current_game", return_value=None), \
         patch.object(game_mod.dal_table, "seated_monikers", return_value=[]), \
         patch.object(dal_player, "get_player_balance", side_effect=ValueError("no credits recorded for alice")):
        state = svc.get_game_state("blackjack-jam", "alice").to_dict()
    assert state["phase"] == "waiting"
    assert state["balance"] is None
