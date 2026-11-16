"""Slice 3: the GameService's refusal-heavy methods return ActionResult (front-end-seam, section 3).

hit, stand, double, split and surrender return an ActionResult: ok and code are the contract, message is
display text, and the method's payload is data. The wire reply is still built by api/results.to_wire, so
the client sees the same dict as before.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from bbsengine6.seam.results import ActionResult
from casino.api import results as _res
from casino.services import game as game_mod


def res_refusal(message):
    """The ActionResult a capability check returns for a refusal message."""
    return _res.refusal_from_message(message)

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
         patch.object(game_mod.dal_game, "get_player_hands", return_value=[hand]), \
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
         patch.object(game_mod.dal_game, "get_player_hands", return_value=[hand]), \
         patch.object(game_mod.dal_game, "update_hand_status"), \
         patch.object(svc, "_all_hands_acted", return_value=False):
        r = svc.stand("t1", "alice")
    assert r.ok is True and r.code == "ok"
    assert r.data["total"] == 17 and r.data["status"] == "standing"
    assert r.message == "Stood at 17"


def test_double_refusal_is_an_action_result_with_its_code():
    svc = _service()
    with patch.object(game_mod.dal_game, "get_active_game", return_value=None):
        r = svc.double("t1", "alice")
    assert isinstance(r, ActionResult)
    assert r.ok is False and r.code == "no_active_game" and r.message == "No active game"


def test_double_refused_by_can_double_keeps_its_code():
    # can_double's own refusal (here: not exactly two cards) reaches the caller with its code.
    svc = _service()
    game = {"id": 9, "status": "player", "tablemoniker": "t1"}
    with patch.object(game_mod.dal_game, "get_active_game", return_value=game), \
         patch.object(svc, "_round_expired", return_value=False), \
         patch.object(svc, "can_double", return_value=res_refusal("Can only double with exactly 2 cards")):
        r = svc.double("t1", "alice")
    assert r.ok is False and r.code == "cannot_double"
    assert r.message == "Can only double with exactly 2 cards"


def test_split_refusal_is_an_action_result_with_its_code():
    svc = _service()
    with patch.object(game_mod.dal_game, "get_active_game", return_value=None):
        r = svc.split("t1", "alice")
    assert isinstance(r, ActionResult)
    assert r.ok is False and r.code == "no_active_game" and r.message == "No active game"


def test_split_refused_by_can_split_keeps_its_code():
    svc = _service()
    game = {"id": 9, "status": "player", "tablemoniker": "t1"}
    with patch.object(game_mod.dal_game, "get_active_game", return_value=game), \
         patch.object(svc, "_round_expired", return_value=False), \
         patch.object(svc, "can_split", return_value=res_refusal("Cards must have same rank to split")):
        r = svc.split("t1", "alice")
    assert r.ok is False and r.code == "cannot_split"
    assert r.message == "Cards must have same rank to split"


def test_surrender_refusal_is_an_action_result_with_its_code():
    svc = _service()
    with patch.object(game_mod.dal_game, "get_active_game", return_value=None):
        r = svc.surrender("t1", "alice")
    assert isinstance(r, ActionResult)
    assert r.ok is False and r.code == "no_active_game" and r.message == "No active game"


def test_surrender_not_allowed_at_this_table_is_cannot_surrender():
    svc = _service()
    game = {"id": 9, "status": "player", "tablemoniker": "t1"}
    with patch.object(game_mod.dal_game, "get_active_game", return_value=game), \
         patch.object(svc, "_round_expired", return_value=False), \
         patch.object(game_mod.dal_table, "get_table", return_value={"attrs": {"surrender": None}}):
        r = svc.surrender("t1", "alice")
    assert r.ok is False and r.code == "cannot_surrender"
    assert r.message == "Surrender not allowed at this table"


def test_can_double_refusal_is_an_action_result():
    svc = _service()
    with patch.object(game_mod.dal_game, "get_active_game", return_value=None):
        r = svc.can_double("t1", "alice")
    assert isinstance(r, ActionResult)
    assert r.ok is False and r.code == "no_active_game"


def test_can_split_refusal_is_an_action_result():
    svc = _service()
    with patch.object(game_mod.dal_game, "get_active_game", return_value=None):
        r = svc.can_split("t1", "alice")
    assert isinstance(r, ActionResult)
    assert r.ok is False and r.code == "no_active_game"
