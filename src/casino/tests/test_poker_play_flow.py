# casino/tests/test_poker_play_flow.py
# The poker play flow a human sees: replies render (not dropped), play seats and opens the menu,
# showdown results are shown, and the submenu offers the actions a player needs.

from __future__ import annotations

import argparse
import asyncio
from unittest.mock import MagicMock, patch

import pytest

from casino.client import casino_client as cc
from casino.commands.poker import lib as poker_lib
from casino.services.poker import PokerService


def _client():
    args = argparse.Namespace(databasename="zoid6test", debug=False)
    client = cc.CasinoClient.__new__(cc.CasinoClient)
    client.args = args
    client.moniker = "bjbed_a"
    client.current_table_moniker = None
    client.last_poker_table = None
    return client


def _capture():
    lines = []
    return lines, patch.object(cc.io, "echo", side_effect=lambda *a, **k: lines.append(" ".join(str(x) for x in a)))


def test_every_poker_reply_type_is_rendered_not_dropped():
    """Each reply type the daemon sends must reach the human (no unknown-type fallthrough)."""
    client = _client()
    for msg_type in cc.POKER_REPLY_TYPES:
        lines, patcher = _capture()
        with patcher:
            asyncio.run(client.handle_message({"type": msg_type, "success": True, "table_moniker": "poker-1",
                                               "stakes": "$1/$2", "message": "ok", "game_stage": "waiting",
                                               "players": [], "community_cards": [], "pot": 0,
                                               "current_bet": 0, "player_hand": [], "current_player": None,
                                               "player_can_act": False, "variant": "texas_hold_em"}))
        assert lines, f"{msg_type} rendered nothing"
        assert not any("Unknown message type" in x for x in lines), msg_type


def test_table_created_records_the_table_for_play():
    client = _client()
    lines, patcher = _capture()
    with patcher:
        asyncio.run(client.handle_message({"type": "poker_table_created", "table_moniker": "poker-7",
                                           "stakes": "$1/$2"}))
    assert client.last_poker_table == "poker-7"
    assert any("poker-7" in x for x in lines)


def test_state_shows_board_pot_seats_and_turn():
    client = _client()
    state = {
        "type": "poker_state", "table_moniker": "poker-1", "variant": "texas_hold_em", "stakes": "$1/$2",
        "game_stage": "flop", "community_cards": ["7S", "KC", "4H"], "pot": 14, "current_bet": 4,
        "player_hand": ["JS", "3C"], "player_can_act": True, "current_player": "bjbed_a",
        "players": [
            {"moniker": "bjbed_a", "seat": 1, "credits": 486, "current_bet": 4, "has_folded": False, "is_all_in": False},
            {"moniker": "bjbed_b", "seat": 2, "credits": 490, "current_bet": 4, "has_folded": True, "is_all_in": False},
        ],
    }
    lines, patcher = _capture()
    with patcher:
        asyncio.run(client.handle_message(state))
    text = "\n".join(lines)
    assert "7S KC 4H" in text
    assert "Pot: $14" in text
    assert "Your cards: JS 3C" in text
    assert "to act" in text and "folded" in text
    assert "It is your turn." in text


def test_showdown_result_is_shown_with_every_hand_and_the_winner():
    client = _client()
    result = {
        "kind": "showdown", "winners": ["bjbed_b"], "pot": 14, "hand_name": "Two Pair",
        "community_cards": ["7S", "KC", "4H", "7H", "8D"],
        "hands": {
            "bjbed_a": {"hole_cards": ["JS", "3C"], "best": ["JS", "7S", "KC", "7H", "8D"], "rank": "Pair"},
            "bjbed_b": {"hole_cards": ["KS", "JH"], "best": ["KS", "JH", "7S", "KC", "7H"], "rank": "Two Pair"},
        },
    }
    lines, patcher = _capture()
    with patcher:
        asyncio.run(client.handle_message({"type": "poker_action_result", "success": True,
                                           "action": "call", "table_moniker": "poker-1",
                                           "last_result": result}))
    text = "\n".join(lines)
    assert "Showdown" in text
    assert "bjbed_a: JS 3C -> Pair" in text
    assert "bjbed_b: KS JH -> Two Pair" in text
    assert "bjbed_b wins $14 with Two Pair" in text


def test_fold_result_tells_the_folding_player_the_outcome():
    client = _client()
    lines, patcher = _capture()
    with patcher:
        asyncio.run(client.handle_message({"type": "poker_action_result", "success": True, "action": "fold",
                                           "winner": "bjbed_b", "pot": 9, "table_moniker": "poker-1"}))
    assert any("You folded. bjbed_b wins $9." in x for x in lines)


def test_refused_action_shows_the_reason():
    client = _client()
    lines, patcher = _capture()
    with patcher:
        asyncio.run(client.handle_message({"type": "poker_action_result", "success": False,
                                           "message": "Not your turn", "table_moniker": "poker-1"}))
    assert any("Not your turn" in x for x in lines)


def test_play_seats_the_player_and_opens_the_menu():
    """play creates a table, seats the player, then opens the poker submenu on that table."""
    client = _client()
    sent = []

    def fake_send(msg):
        sent.append(msg)
        if msg["type"] == "poker_create_table":
            client.last_poker_table = "poker-9"
        return asyncio.sleep(0)

    client.send = fake_send
    client._loop = asyncio.new_event_loop()
    try:
        with patch.object(poker_lib, "get_client", return_value=client), \
             patch.object(poker_lib.io, "inputinteger", return_value=100), \
             patch.object(poker_lib, "menu", return_value=True) as menu, \
             patch.object(poker_lib.io, "echo"):
            ok = poker_lib.play(argparse.Namespace(), client=client)
    finally:
        client._loop.close()

    assert ok is True
    assert [m["type"] for m in sent] == ["poker_create_table", "poker_join_table"]
    join = sent[1]
    assert join["table_moniker"] == "poker-9" and join["buy_in"] == 100
    assert client.current_table_moniker == "poker-9"
    menu.assert_called_once()


def test_play_refuses_a_bad_buy_in_without_creating_a_table():
    client = _client()
    client.send = MagicMock()
    client._loop = asyncio.new_event_loop()
    try:
        with patch.object(poker_lib.io, "inputinteger", return_value=0), \
             patch.object(poker_lib.io, "echo"):
            ok = poker_lib.play(argparse.Namespace(), client=client)
    finally:
        client._loop.close()
    assert ok is False
    client.send.assert_not_called()


def test_submenu_offers_the_actions_a_player_needs():
    """The submenu must offer start, check, call, bet, raise, all-in, fold, table, and quit."""
    keys = []

    def fake_choice(prompt, choices, default=None, help=None, **kwargs):
        keys.append(choices)
        return "Q"

    with patch.object(poker_lib.io, "inputchoice", side_effect=fake_choice):
        poker_lib.menu(argparse.Namespace(), client=MagicMock(_loop=None))
    assert keys == ["s,c,l,b,r,a,f,t,q"]


def test_submenu_start_and_call_send_the_daemon_messages():
    """Start and call in the submenu send the poker messages the daemon handles."""
    client = MagicMock()
    client._loop = asyncio.new_event_loop()
    sent = []
    client.send = lambda msg: (sent.append(msg), asyncio.sleep(0))[1]
    choices = iter(["S", "L", "Q"])
    try:
        with patch.object(poker_lib.io, "inputchoice", side_effect=lambda *a, **k: next(choices)), \
             patch.object(poker_lib.io, "echo"):
            poker_lib.menu(argparse.Namespace(), client=client)
    finally:
        client._loop.close()
    assert [m["type"] for m in sent] == ["poker_start_hand", "poker_call"]


def _two_player_table(name: str):
    svc = PokerService(argparse.Namespace(databasename="zoid6test", debug=False))
    svc.create_table(table_moniker=name, variant_name="holdem", betting_structure="no_limit",
                     small_blind=1, big_blind=2)
    for m in ("bjbed_a", "bjbed_b"):
        svc.join_table(name, m, 100)
    svc.start_hand(name)
    return svc, svc._tables[name]


def test_reraise_charges_only_the_difference_and_conserves_chips():
    """A raise is a total for the street: the pot grows by the difference, never double counts."""
    svc, t = _two_player_table("acct-reraise")
    first = t.current_player
    assert svc.player_action("acct-reraise", first, "raise", 6)["success"]
    assert t.players[first].current_bet == 6
    second = t.current_player
    assert svc.player_action("acct-reraise", second, "raise", 10)["success"]
    # Pot = 2 (small blind) + 1 (big blind) ... committed totals: 6 and 10 this street.
    assert t.players[first].total_in_pot == 6
    assert t.players[second].total_in_pot == 10
    assert t.pot == sum(p.total_in_pot for p in t.players.values())
    assert sum(p.credits for p in t.players.values()) + t.pot == 200


def test_raise_below_current_bet_plus_big_blind_is_refused():
    svc, t = _two_player_table("acct-min")
    first = t.current_player
    res = svc.player_action("acct-min", first, "raise", 3)
    assert res["success"] is False
    assert "Minimum" in res["message"]


def test_fold_win_sets_last_result_with_the_pot_and_winner():
    """A fold that ends the hand must record it, the same as a showdown does."""
    svc, t = _two_player_table("lr-fold")
    cur = t.current_player
    other = "bjbed_b" if cur == "bjbed_a" else "bjbed_a"
    assert svc.player_action("lr-fold", cur, "raise", 6)["success"]
    assert svc.player_action("lr-fold", other, "fold")["success"]
    lr = svc.last_result("lr-fold")
    assert lr is not None
    assert lr["kind"] == "uncontested"
    assert lr["winners"] == [cur]
    assert lr["pot"] == sum(lr["shares"].values())
    assert lr["shares"] == {cur: lr["pot"]}


def test_showdown_last_result_shares_add_up_to_the_pot():
    svc, t = _two_player_table("lr-show")
    cur = t.current_player
    svc.player_action("lr-show", cur, "raise", 6)
    svc.player_action("lr-show", t.current_player, "call")
    while t.game_stage != "showdown":
        svc.player_action("lr-show", t.current_player, "check")
    lr = svc.last_result("lr-show")
    assert lr["kind"] == "showdown"
    assert sum(lr["shares"].values()) == lr["pot"]
    assert set(lr["winners"]) == set(lr["shares"])
    assert set(lr["hands"]) == {"bjbed_a", "bjbed_b"}
    assert t.pot == 0


def test_split_pot_gives_the_odd_chip_to_the_first_seat_and_sums_to_the_pot():
    from casino.poker.player import PokerPlayer

    svc = PokerService(argparse.Namespace(databasename="zoid6test", debug=False))
    svc.create_table(table_moniker="lr-split", variant_name="holdem", betting_structure="no_limit",
                     small_blind=1, big_blind=2)
    t = svc._tables["lr-split"]
    for seat, m in enumerate(("bjbed_a", "bjbed_b"), 1):
        p = PokerPlayer(moniker=m, seat=seat, credits=100)
        p.hole_cards = ["2C", "3D"]
        t.players[m] = p
    t.community_cards = ["AS", "KS", "QS", "JS", "TS"]
    t.pot = 7
    t.game_stage = "river"
    svc._showdown(t)
    lr = t.last_result
    assert lr["winners"] == ["bjbed_a", "bjbed_b"]
    assert lr["shares"] == {"bjbed_a": 4, "bjbed_b": 3}
    assert sum(lr["shares"].values()) == 7
    assert t.pot == 0


def test_renderer_shows_each_split_share():
    client = _client()
    result = {"kind": "showdown", "winners": ["bjbed_a", "bjbed_b"], "pot": 7,
              "shares": {"bjbed_a": 4, "bjbed_b": 3}, "hand_name": "Flush",
              "hands": {}, "community_cards": []}
    lines, patcher = _capture()
    with patcher:
        client._render_last_result(result)
    assert any("bjbed_a $4" in x and "bjbed_b $3" in x for x in lines)


def _showdown_table(name: str, hands: dict, board: list, pot: int = 4):
    from casino.poker.player import PokerPlayer

    svc = PokerService(argparse.Namespace(databasename="zoid6test", debug=False))
    svc.create_table(table_moniker=name, variant_name="holdem", betting_structure="no_limit",
                     small_blind=1, big_blind=2)
    t = svc._tables[name]
    for seat, (m, h) in enumerate(hands.items(), 1):
        p = PokerPlayer(moniker=m, seat=seat, credits=100)
        p.hole_cards = h
        t.players[m] = p
    t.community_cards = board
    t.pot = pot
    t.game_stage = "river"
    svc._showdown(t)
    return t


def test_higher_pair_beats_lower_pair_on_the_same_category():
    """Pair of 7s beats pair of 6s. The category alone (both Pair) must not award a split."""
    t = _showdown_table("sd-pair", {"bjbed_a": ["6C", "KS"], "bjbed_b": ["7S", "9S"]},
                        ["8S", "QH", "7C", "AH", "6H"], pot=4)
    assert t.last_result["winners"] == ["bjbed_b"]
    assert t.last_result["shares"] == {"bjbed_b": 4}
    assert t.players["bjbed_b"].credits == 104
    assert t.players["bjbed_a"].credits == 100


def test_identical_board_hands_split_the_pot():
    """Two players playing the board (royal flush) tie and split."""
    t = _showdown_table("sd-tie", {"bjbed_a": ["2C", "3D"], "bjbed_b": ["2H", "4S"]},
                        ["10S", "JS", "QS", "KS", "AS"], pot=8)
    assert set(t.last_result["winners"]) == {"bjbed_a", "bjbed_b"}
    assert sum(t.last_result["shares"].values()) == 8
    assert t.last_result["hand_name"] == "Royal Flush"


def test_kicker_decides_between_equal_pairs():
    """Same pair value, different kicker: the higher kicker wins outright."""
    t = _showdown_table("sd-kicker", {"bjbed_a": ["9C", "2D"], "bjbed_b": ["9S", "KD"]},
                        ["9H", "5C", "7D", "3S", "JH"], pot=6)
    assert t.last_result["winners"] == ["bjbed_b"]
    assert t.players["bjbed_b"].credits == 106
