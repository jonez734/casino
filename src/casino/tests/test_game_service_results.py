"""Slice 3: the GameService's refusal-heavy methods return ActionResult (front-end-seam, section 3).

hit, stand, double, split and surrender return an ActionResult: ok and code are the contract, message is
display text, and the method's payload is data. The wire reply is still built by api/results.to_wire, so
the client sees the same dict as before.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from bbsengine6.seam.results import ActionResult
from casino.services import game as game_mod

pytestmark = pytest.mark.unit


def _service():
    svc = game_mod.GameService.__new__(game_mod.GameService)
    svc.args = SimpleNamespace()
    svc._pool = None
    return svc


def test_hit_refusal_is_an_action_result_with_its_code():
    svc = _service()
    with patch.object(game_mod.dal_game, "get_active_game", return_value=None):
        r = svc.hit("t1", "alice")
    assert isinstance(r, ActionResult)
    assert r.ok is False and r.code == "no_active_game" and r.message == "No active game"


def test_hit_success_carries_its_payload_in_data():
    svc = _service()
    game = {"id": 9, "status": "player", "tablemoniker": "t1"}
    hand = {"id": 3, "cards": ["2H", "5D"], "playermoniker": "alice"}
    table = {"attrs": {}}
    with patch.object(game_mod.dal_game, "get_active_game", return_value=game), \
         patch.object(svc, "_round_expired", return_value=False), \
         patch.object(game_mod.dal_game, "get_player_hand", return_value=hand), \
         patch.object(svc, "_draw_card", return_value="7S"), \
         patch.object(game_mod.dal_game, "update_hand_cards"), \
         patch.object(game_mod.dal_game, "update_hand_status"), \
         patch.object(game_mod.dal_table, "get_table", return_value=table):
        r = svc.hit("t1", "alice")
    assert r.ok is True and r.code == "ok"
    assert r.data["cards"] == ["2H", "5D", "7S"] and r.data["total"] == 14


def test_hit_refusals_map_to_the_same_codes_as_before():
    from casino.api import results as res

    svc = _service()
    with patch.object(game_mod.dal_game, "get_active_game", return_value={"id": 9}), \
         patch.object(svc, "_round_expired", return_value=True):
        r = svc.hit("t1", "alice")
    assert r.code == res.code_for_message("The round clock expired")


def test_stand_refusal_is_an_action_result_with_its_code():
    svc = _service()
    with patch.object(game_mod.dal_game, "get_active_game", return_value=None):
        r = svc.stand("t1", "alice")
    assert isinstance(r, ActionResult)
    assert r.ok is False and r.code == "no_active_game" and r.message == "No active game"


def test_stand_success_carries_total_and_status_in_data():
    svc = _service()
    game = {"id": 9, "status": "player", "tablemoniker": "t1"}
    hand = {"id": 3, "cards": ["10H", "7D"], "playermoniker": "alice"}
    with patch.object(game_mod.dal_game, "get_active_game", return_value=game), \
         patch.object(svc, "_round_expired", return_value=False), \
         patch.object(game_mod.dal_game, "get_player_hand", return_value=hand), \
         patch.object(game_mod.dal_game, "update_hand_status"), \
         patch.object(svc, "_all_hands_acted", return_value=False):
        r = svc.stand("t1", "alice")
    assert r.ok is True and r.code == "ok"
    assert r.data["total"] == 17 and r.data["status"] == "standing"
    assert r.message == "Stood at 17"
