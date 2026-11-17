""""Your hand" shows the player's hand still in play, not a finished one that came earlier in the round.

A player can hold a busted hand and then an open one in the same round. The displayed hand used to be the first hand
(the busted one), while the actions were offered for the open one, so the screen contradicted itself.
"""

from casino.services import game as game_mod


def test_the_shown_hand_is_the_open_one_when_an_earlier_hand_is_finished():
    hands = [
        {"cards": ["8C", "4D", "10S"], "status": "bust", "total": 22},
        {"cards": ["5S", "6S"], "status": None, "total": 11},
    ]
    assert game_mod.shown_hand(hands) == hands[1]


def test_with_only_finished_hands_the_last_one_is_shown():
    hands = [
        {"cards": ["8C", "4D", "10S"], "status": "bust", "total": 22},
        {"cards": ["9H", "9D"], "status": "standing", "total": 18},
    ]
    assert game_mod.shown_hand(hands) == hands[1]


def test_with_no_hands_nothing_is_shown():
    assert game_mod.shown_hand([]) is None
