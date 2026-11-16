"""The game state lists only the actions the player can take now, as ``available_actions``.

The client's action prompt and its tab completion are built from that list, so a refused action is never
offered. Hit, stand, double, split and surrender come from the player's open hand's flags; a bet is offered only
when no hand is in play. A finished round offers nothing.
"""

from types import SimpleNamespace

import pytest

from casino.services import game as game_mod


pytestmark = pytest.mark.unit


def _hand(**flags):
    base = {"hand_id": 1, "status": None, "can_hit": False, "can_stand": False,
            "can_double": False, "can_split": False, "can_surrender": False}
    base.update(flags)
    return base


@pytest.mark.parametrize("flags,expected", [
    (dict(can_hit=True, can_stand=True, can_double=True, can_split=True, can_surrender=True),
     ["hit", "stand", "double", "split", "surrender"]),
    (dict(can_hit=True, can_stand=True, can_double=False, can_split=False, can_surrender=False), ["hit", "stand"]),
    (dict(), []),
])
def test_actions_follow_the_open_hand_flags(flags, expected):
    assert game_mod.available_actions_for([_hand(**flags)], bet_allowed=False) == expected


def test_bet_is_offered_only_when_no_hand_is_in_play():
    assert game_mod.available_actions_for([], bet_allowed=True) == ["bet"]
    assert "bet" not in game_mod.available_actions_for([_hand(can_hit=True)], bet_allowed=False)


def test_a_busted_hand_offers_no_action():
    busted = _hand(status="bust", can_hit=False, can_stand=False, can_double=False, can_split=False,
                   can_surrender=False)
    assert game_mod.available_actions_for([busted], bet_allowed=False) == []
