"""A hit that busts stores the bust result on the hand at once, so the table can say so mid-round.

The hit marked the hand 'bust' but wrote no result, so until the round settled nothing said the hand was over. The bust
now records its result (the loss the player takes) on the hand, the same way settlement does.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from casino.dal import game as dal_game
from casino.services import game as game_mod


pytestmark = pytest.mark.unit


def test_a_bust_on_hit_stores_the_bust_result_on_the_hand():
    svc = game_mod.GameService.__new__(game_mod.GameService)
    svc.args = SimpleNamespace()
    svc._pool = None
    stored = []
    with patch.object(dal_game, "merge_hand_result", lambda args, hid, result, **k: stored.append((hid, result))), \
         patch.object(dal_game, "update_hand_status", lambda *a, **k: None):
        svc._record_bust(hand_id=348, bet_amount=10)
    assert stored == [(348, {"result": "bust", "reason": "player_bust", "net": -10,
                              "text": "you busted, bet 10, net -10"})]
