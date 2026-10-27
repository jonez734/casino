#!/usr/bin/env python3
# casino/tests/test_multi_seat_round.py
# Phase 4 slice 5a: a blackjack round with several seats settles once, after every seated hand has
# acted. One player standing must not end the round for the others. Stubbed: no database.

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from casino.dal import game as dal_game
from casino.services import game as game_mod


def _service():
    svc = game_mod.GameService.__new__(game_mod.GameService)
    svc.args = SimpleNamespace()
    svc._pool = None
    return svc


def _hands(*statuses):
    return [
        {"id": i + 1, "playermoniker": f"p{i}", "cards": ["AH", "KD"], "attrs": {"status": s} if s else {}}
        for i, s in enumerate(statuses)
    ]


@pytest.mark.unit
def test_round_is_not_done_while_a_seat_is_still_open():
    svc = _service()
    with patch.object(dal_game, "get_game_hands", return_value=_hands("standing", None)):
        assert svc._all_hands_acted({"id": 7}) is False


@pytest.mark.unit
def test_round_is_done_once_every_seat_has_acted():
    svc = _service()
    with patch.object(dal_game, "get_game_hands", return_value=_hands("standing", "bust", "surrendered")):
        assert svc._all_hands_acted({"id": 7}) is True


@pytest.mark.unit
def test_a_single_player_round_is_done_when_that_player_acts():
    svc = _service()
    with patch.object(dal_game, "get_game_hands", return_value=_hands("standing")):
        assert svc._all_hands_acted({"id": 7}) is True


@pytest.mark.unit
def test_stand_does_not_settle_while_another_seat_is_open():
    svc = _service()
    game = {"id": 7, "status": "player"}
    hand = {"id": 1, "cards": ["AH", "KD"], "attrs": {}}
    with patch.object(dal_game, "get_active_game", return_value=game), \
         patch.object(svc, "_round_expired", return_value=False), \
         patch.object(dal_game, "get_player_hand", return_value=hand), \
         patch.object(dal_game, "get_game_hands", return_value=_hands(None, None)), \
         patch.object(dal_game, "update_hand_status") as mark, \
         patch.object(svc, "settle_game") as settle:
        result = svc.stand("blackjack-x", "p0")
    settle.assert_not_called()
    mark.assert_called_once()  # this seat is marked standing, the round is not settled
    assert result["success"] is True


@pytest.mark.unit
def test_stand_settles_once_the_last_seat_acts():
    svc = _service()
    game = {"id": 7, "status": "player"}
    hand = {"id": 2, "cards": ["AH", "KD"], "attrs": {}}
    # p1 is the last open seat. After stand marks it, every seat has acted.
    hands = _hands("standing", None)
    marked = {"done": False}

    def fake_update(args, hand_id, attrs, pool=None):
        if hand_id == 2:
            hands[1]["attrs"] = attrs
            marked["done"] = True

    with patch.object(dal_game, "get_active_game", return_value=game), \
         patch.object(svc, "_round_expired", return_value=False), \
         patch.object(dal_game, "get_player_hand", return_value=hand), \
         patch.object(dal_game, "get_game_hands", side_effect=lambda *a, **k: hands), \
         patch.object(dal_game, "update_hand_status", side_effect=lambda a, hid, st, pool=None: fake_update(a, hid, {"status": st})), \
         patch.object(svc, "settle_game") as settle:
        svc.stand("blackjack-x", "p1")
    assert marked["done"] is True
    settle.assert_called_once_with("blackjack-x")


@pytest.mark.unit
def test_stand_merges_its_status_and_keeps_other_hand_attrs():
    # update_hand_attrs replaces the whole attrs object, which would drop keys such as split_count.
    # stand must only set its own status, the way hit and bust do.
    svc = _service()
    game = {"id": 7, "status": "player"}
    hand = {"id": 1, "cards": ["AH", "KD"], "attrs": {"split_count": 1}}
    with patch.object(dal_game, "get_active_game", return_value=game), \
         patch.object(svc, "_round_expired", return_value=False), \
         patch.object(dal_game, "get_player_hand", return_value=hand), \
         patch.object(dal_game, "get_game_hands", return_value=_hands("standing")), \
         patch.object(dal_game, "update_hand_status") as set_status, \
         patch.object(dal_game, "update_hand_attrs") as replace_attrs, \
         patch.object(svc, "settle_game"):
        svc.stand("blackjack-x", "p0")
    set_status.assert_called_once()
    replace_attrs.assert_not_called()


@pytest.mark.unit
def test_a_second_seats_bet_joins_the_open_round_instead_of_starting_one():
    svc = _service()
    game = {"id": 7, "status": "player"}
    with patch.object(dal_game, "get_active_game", return_value=game), \
         patch.object(game_mod.dal_table, "get_table", return_value={"minimumbet": 1, "maximumbet": 100}), \
         patch.object(game_mod.dal_bet, "place_bet", return_value={"id": 5}) as place, \
         patch.object(dal_game, "create_hand", return_value={"id": 9}), \
         patch.object(dal_game, "update_hand_cards"), \
         patch.object(game_mod.dal_bet, "update_bet_hand_id"), \
         patch.object(game_mod.dal_bet, "update_bet_currenthand"), \
         patch.object(svc, "_draw_card", return_value="2C"), \
         patch.object(svc, "start_game") as start:
        result = svc.place_bet("blackjack-x", "p1", 10)
    start.assert_not_called()  # the round is already open
    place.assert_called_once()
    # place_bet(args, player, table, game_id, amount): the bet is recorded against the open game.
    assert place.call_args.args[3] == 7
    assert result["success"] is True


@pytest.mark.unit
def test_round_clock_expiry_penalises_each_open_seat_and_settles_once():
    from casino.services import round_clock as rc

    svc = _service()
    hands = [
        {"id": 11, "playermoniker": "alice", "attrs": {"status": "standing"}},
        {"id": 12, "playermoniker": "bob", "attrs": {}},
        {"id": 13, "playermoniker": "bot_x_1", "attrs": {}},
    ]
    bets = {11: {"id": 1, "status": "pending", "amount": 10},
            12: {"id": 2, "status": "pending", "amount": 10},
            13: {"id": 3, "status": "pending", "amount": 10}}
    with patch.object(dal_game_mod_round(), "get_active_game", return_value={"id": 7}), \
         patch.object(dal_table_mod_round(), "get_table", return_value={"clock_penalty": "skip"}), \
         patch.object(dal_game_mod_round(), "get_game_hands", return_value=hands), \
         patch.object(dal_bet_mod_round(), "get_bet_for_hand", side_effect=lambda a, hid, pool=None: bets[hid]), \
         patch.object(rc, "log_expiry") as log, \
         patch.object(svc, "settle_game") as settle:
        out = rc.expire_round(svc, "t1")
    # Alice already stood, so only the two open seats are penalised; the round settles once.
    assert out["expired"] == 2
    assert log.call_count == 2
    settle.assert_called_once_with("t1")


def dal_game_mod_round():
    from casino.dal import game as g
    return g


def dal_table_mod_round():
    from casino.dal import table as t
    return t


def dal_bet_mod_round():
    from casino.dal import bet as b
    return b


@pytest.mark.unit
def test_game_state_lists_every_seat_with_its_acted_state():
    svc = _service()
    table = {"moniker": "blackjack-x", "attrs": {}, "type": "blackjack"}
    game = {"id": 7, "status": "player", "table_moniker": "blackjack-x"}
    round_hands = [
        {"id": 11, "playermoniker": "alice", "cards": ["AH", "KD"], "attrs": {"status": "standing"}},
        {"id": 12, "playermoniker": "bob", "cards": ["5H", "6D"], "attrs": {}},
    ]
    with patch.object(dal_game, "get_current_game", return_value=game), \
         patch.object(game_mod.dal_table, "get_table", return_value=table), \
         patch.object(dal_game, "get_player_hands", return_value=[round_hands[1]]), \
         patch.object(dal_game, "get_game_hands", return_value=round_hands), \
         patch.object(dal_game, "get_dealer_hand", return_value=None), \
         patch.object(game_mod.dal_bet, "get_bet_for_hand", return_value={"amount": 10, "id": 1}), \
         patch.object(svc, "_is_dealer_showing_ace", return_value=False), \
         patch.object(svc, "_draw_card", return_value="2C"), \
         patch.object(dal_game, "create_dealer_hand"), \
         patch.object(dal_game, "update_dealer_hand_cards"), \
         patch.object(dal_game, "set_dealer_hole_card", create=True), \
         patch.object(game_mod.dal_bet, "get_insurance", return_value=None), \
         patch.object(svc, "_hide_hole_card", return_value=[]):
        state = svc.get_game_state("blackjack-x", "bob")
    seats_view = {s["player"]: s for s in state["seats"]}
    assert seats_view["alice"]["acted"] is True
    assert seats_view["bob"]["acted"] is False
    assert len(state["seats"]) == 2
