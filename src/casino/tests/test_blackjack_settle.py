#!/usr/bin/env python3
# casino/tests/test_blackjack_settle.py
# How a blackjack hand ends. classify_hand and describe are shared by BED and door mode, so these
# pins cover the rules once and the parity tests check that both modes use them. Stubbed: no DB.

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from casino.blackjack import settle
from casino.blackjack.settle import classify_hand, describe
from casino.dal import bet as dal_bet
from casino.dal import game as dal_game
from casino.dal import table as dal_table
from casino.services import game as game_mod
from casino.services import round_clock as rc


# ---- classify_hand: every ending in the table --------------------------------------------------

CLASSIFY_CASES = [
    # (player, dealer, player_status, expected outcome, expected reason)
    (["AH", "KD"], ["AS", "QC"], None, "push", "both_natural"),
    (["AH", "KD"], ["9S", "7C", "5D"], None, "blackjack", "player_natural"),
    (["9H", "7D", "5C"], ["KS", "QC"], None, "win", "higher_total"),
    (["KH", "9D"], ["AS", "QC"], None, "loss", "dealer_natural"),
    (["10H", "6D", "9C"], ["KS", "QC"], None, "bust", "player_bust"),
    (["KH", "QD", "5D"], ["10H", "7D"], None, "bust", "player_bust"),
    (["10H", "7D"], ["KH", "QD", "5D"], None, "win", "dealer_bust"),
    (["2H", "3D", "4C", "5S", "6H"], ["KS", "9C"], "charlie", "win", "charlie"),
    (["10H", "9D"], ["10H", "7D"], None, "win", "higher_total"),
    (["10H", "7D"], ["10H", "9D"], None, "loss", "lower_total"),
    (["10H", "8D"], ["KH", "8C"], None, "push", "push_total"),
]


@pytest.mark.unit
@pytest.mark.parametrize("player,dealer,status,outcome,reason", CLASSIFY_CASES)
def test_classify_hand_table(player, dealer, status, outcome, reason):
    assert classify_hand(player, dealer, player_status=status) == (outcome, reason)


@pytest.mark.unit
def test_dealer_natural_beats_a_three_card_21():
    # The rule the table reported: dealer natural 21 vs player 21 made with three cards.
    assert classify_hand(["10H", "6D", "5C"], ["AS", "KD"]) == ("loss", "dealer_natural")


@pytest.mark.unit
def test_natural_beats_a_non_natural_21_for_the_player():
    assert classify_hand(["AH", "KD"], ["10S", "7C", "4D"]) == ("blackjack", "player_natural")


@pytest.mark.unit
def test_hand_total_counts_aces_down_as_needed():
    assert settle.hand_total(["AH", "9D", "5C"]) == 15
    assert settle.hand_total(["AH", "AD", "9C"]) == 21


# ---- describe: the one-line ending each reason produces ---------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("reason,expected", [
    ("both_natural", "both natural blackjack, bet 10, net 0"),
    ("dealer_natural", "dealer natural blackjack, bet 10, net -10"),
    ("player_natural", "player natural blackjack, bet 10, net +10"),
    ("player_bust", "you busted with 25, bet 10, net -10"),
    ("dealer_bust", "dealer busted with 22, bet 10, net +10"),
    ("charlie", "five-card Charlie, bet 10, net +10"),
    ("higher_total", "you 20, dealer 18, bet 10, net +10"),
    ("lower_total", "you 17, dealer 19, bet 10, net -10"),
    ("push_total", "push at 18, bet 10, net 0"),
    ("player_quit", "you quit the hand, bet 10, net -10"),
])
def test_describe_text_per_reason(reason, expected):
    player = {
        "player_bust": ["KH", "QD", "5D"],
        "higher_total": ["10H", "KD"],
        "lower_total": ["10H", "7D"],
        "push_total": ["10H", "8D"],
        "charlie": ["2H", "3D", "4C", "5S", "6H"],
        "player_natural": ["AH", "KD"],
        "both_natural": ["AH", "KD"],
    }.get(reason, ["10H", "7D"])
    dealer = {
        "dealer_natural": ["AS", "KD"],
        "both_natural": ["AS", "QC"],
        "dealer_bust": ["KH", "QD", "2D"],
        "higher_total": ["10S", "8C"],
        "lower_total": ["10S", "9C"],
        "push_total": ["10S", "8C"],
    }.get(reason, ["10S", "8C"])
    text = describe(reason, player_cards=player, dealer_cards=dealer, bet=10,
                    net={"dealer_natural": -10, "lower_total": -10, "player_bust": -10,
                         "player_quit": -10, "both_natural": 0, "push_total": 0}.get(reason, 10))
    assert text == expected


@pytest.mark.unit
def test_describe_standup_and_surrender():
    assert describe("standup", player_cards=[], dealer_cards=[], bet=10, net=0) == \
        "standup, bet 10 refunded, net 0"
    assert describe("surrender", player_cards=["10H", "6D"], dealer_cards=["KS", "9C"],
                    bet=10, net=-5, returned=5) == "surrendered, bet 10, returned 5, net -5"


@pytest.mark.unit
def test_zero_net_never_renders_as_plus_zero():
    assert "+0" not in describe("push_total", player_cards=["10H", "8D"], dealer_cards=["10S", "8C"],
                                bet=10, net=0)


# ---- settle_game: surrender and standup seats ------------------------------------------------

def _service():
    svc = game_mod.GameService.__new__(game_mod.GameService)
    svc.args = SimpleNamespace()
    svc._pool = None
    return svc


def _run_settle(svc, hands, bets, dealer_cards, *, insurance=0):
    game = {"id": 7, "status": "player", "tablemoniker": "blackjack-x", "kind": "blackjack"}
    dealer = {"id": 1, "playermoniker": None, "cards": dealer_cards, "attrs": {"is_dealer": True}}
    settle_bet = MagicMock()
    increment = MagicMock()
    with patch.object(dal_game, "get_active_game", return_value=game), \
         patch.object(dal_game, "get_game_hands", return_value=hands + [dealer]), \
         patch.object(dal_game, "update_game_status"), \
         patch.object(dal_game, "update_game_attrs"), \
         patch.object(dal_table, "get_table", return_value={"attrs": {}}), \
         patch.object(dal_bet, "get_bet_for_hand", side_effect=lambda a, hid, pool=None: bets.get(hid)), \
         patch.object(dal_bet, "get_insurance", return_value=insurance), \
         patch.object(dal_bet, "settle_bet", settle_bet), \
         patch.object(game_mod.dal_player, "increment_stat", increment), \
         patch.object(svc, "_run_dealer_turn", return_value=dealer_cards), \
         patch.object(game_mod, "get_surrender_multiplier", return_value=Decimal("0.5")):
        result = svc.settle_game("blackjack-x")
    return result, settle_bet, increment


def _stats(increment):
    return [c.args[2] for c in increment.call_args_list]


@pytest.mark.unit
def test_surrendered_seat_is_listed_with_its_text_and_no_win_loss_stat():
    svc = _service()
    hands = [{"id": 10, "playermoniker": "jam", "cards": ["10H", "6D"],
              "attrs": {"status": "surrendered"}}]
    bets = {10: {"id": 100, "amount": Decimal("10"), "status": "pending"}}
    result, _, increment = _run_settle(svc, hands, bets, ["KS", "9C"])
    [o] = result["outcomes"]
    assert o["result"] == "surrender"
    assert o["reason"] == "surrender"
    assert o["text"] == "surrendered, bet 10, returned 5, net -5"
    stats = _stats(increment)
    assert "wins" not in stats and "losses" not in stats and "pushes" not in stats
    assert "blackjack.surrenders" in stats


@pytest.mark.unit
def test_standup_seat_is_refunded_listed_and_not_counted():
    svc = _service()
    hands = [{"id": 11, "playermoniker": "alice", "cards": ["10H", "6D"],
              "attrs": {"status": rc.STANDUP_STATUS}}]
    bets = {11: {"id": 101, "amount": Decimal("10"), "status": "pending"}}
    result, settle_bet, increment = _run_settle(svc, hands, bets, ["KS", "9C"])
    [o] = result["outcomes"]
    assert o["result"] == "standup"
    assert o["text"] == "standup, bet 10 refunded, net 0"
    assert o["net"] == 0
    # The standup hand was never played out: no win, loss, push, hand-played, or net stat.
    assert _stats(increment) == []
    # Standup hands are not paid or charged by settle_game; the refund was made by the round clock.
    settle_bet.assert_not_called()


@pytest.mark.unit
def test_standup_is_an_acted_status_so_the_round_can_settle():
    assert rc.STANDUP_STATUS in rc.ACTED_STATUSES


# ---- BED and door mode give the same ending for the same cards -------------------------------

PARITY_CASES = [
    (["AH", "KD"], ["AS", "QC"]),          # both natural
    (["AH", "KD"], ["10S", "7C", "4D"]),   # player natural
    (["10H", "6D", "5C"], ["AS", "KD"]),   # dealer natural vs three-card 21
    (["KH", "QD", "5D"], ["10H", "7D"]),   # player bust
    (["10H", "7D"], ["KH", "QD", "5D"]),   # dealer bust
    (["10H", "9D"], ["10S", "8C"]),        # higher total
    (["10H", "8D"], ["KH", "8C"]),         # equal total
]


def _door_hand(card_strings):
    """A door-mode hand: the same type the door loop uses (casino.lib.Hand)."""
    from casino import lib as libcasino

    hand = libcasino.Hand("test")
    for shorthand in card_strings:
        hand.add(libcasino.Card(shorthand=shorthand, facedown=False))
    return hand


@pytest.mark.unit
@pytest.mark.parametrize("player,dealer", PARITY_CASES)
def test_bed_and_door_mode_end_the_hand_the_same_way(player, dealer):
    from casino.blackjack import play as door
    from casino.blackjack.lib import BlackjackPlayer
    from casino.blackjack.play import determine_winner

    # BED: classify_hand (the function settle_game calls) and its text. Net uses the same payouts
    # as settle_game: blackjack 3:2, win 1:1, push 0, loss and bust lose the bet.
    bed_outcome, bed_reason = classify_hand(player, dealer)
    net = {"blackjack": 15, "win": 10, "push": 0}.get(bed_outcome, -10)
    bed_text = describe(bed_reason, player_cards=player, dealer_cards=dealer, bet=10, net=net)

    # Door mode: determine_winner on the same cards, capturing the echoed ending.
    echoed = []
    p = BlackjackPlayer()
    p.currentbet = 10
    with patch.object(door, "io") as fake_io:
        fake_io.echo.side_effect = lambda s, **k: echoed.append(s)
        determine_winner(_door_hand(player), _door_hand(dealer), p)
    door_line = echoed[0]

    assert f"Result: {bed_outcome} -- {bed_text}" in door_line


@pytest.mark.unit
def test_door_mode_pushes_count_as_pushes_like_bed():
    from casino.blackjack import Hand
    from casino.blackjack.lib import BlackjackPlayer
    from casino.blackjack.play import determine_winner

    p = BlackjackPlayer()
    p.currentbet = 10
    with patch("casino.blackjack.play.io"):
        determine_winner(Hand.from_strings(["10H", "8D"]), Hand.from_strings(["KH", "8C"]), p)
    assert p.stats["blackjack"]["push"] == 1
    assert "draw" not in p.stats["blackjack"]


@pytest.mark.unit
def test_door_mode_quit_is_a_loss_with_its_own_text():
    from casino.blackjack import Hand
    from casino.blackjack.lib import BlackjackPlayer
    from casino.blackjack.play import determine_winner

    p = BlackjackPlayer()
    p.currentbet = 10
    echoed = []
    with patch("casino.blackjack.play.io") as fake_io:
        fake_io.echo.side_effect = lambda s, **k: echoed.append(s)
        determine_winner(Hand.from_strings(["10H", "6D"]), Hand.from_strings(["KS", "9C"]), p,
                         quit_hand=True)
    assert p.stats["blackjack"]["loss"] == 1
    assert "you quit the hand, bet 10, net -10" in echoed[0]
