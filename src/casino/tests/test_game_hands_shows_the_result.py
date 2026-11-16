"""A settled round's result is kept on each hand, and ``game hands`` shows it with the dealer's result.

The settlement built each seat's result, but it was only in memory, so a later look at the hands showed no
outcome. The result is now stored on the hand when it settles, and game hands reports it.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from casino.api.payloads import GameState
from casino.dal import game as dal_game
from casino.services import game as game_mod


pytestmark = pytest.mark.unit


def test_settling_stores_each_hands_result_on_the_hand():
    svc = game_mod.GameService.__new__(game_mod.GameService)
    svc.args = SimpleNamespace()
    svc._pool = None
    stored = []
    with patch.object(dal_game, "merge_hand_result", lambda args, hid, result, **k: stored.append((hid, result))):
        svc._store_hand_result(
            7, {"result": "loss", "reason": "lower_total", "net": -10, "text": "lost 10"},
        )
    assert stored == [(7, {"result": "loss", "reason": "lower_total", "net": -10, "text": "lost 10"})]


def test_game_hands_reports_the_result_and_the_dealer():
    state = GameState.from_dict({
        "table_moniker": "blackjack-jam",
        "phase": "settled",
        "player_hand": ["8D", "QC"],
        "player_total": 18,
        "dealer_hand": ["6D", "JS", "KH"],
        "dealer_total": 26,
        "hands": [{"hand_id": 333, "cards": ["8D", "QC"], "total": 18, "status": "standing", "bet": 10,
                   "result": "loss", "reason": "lower_total", "net": -10}],
    })
    lines = game_mod.describe_hands_result(state)
    text = "\n".join(lines)
    assert "loss" in text.lower()
    assert "-10" in text
    assert "dealer" in text.lower() and "26" in text

