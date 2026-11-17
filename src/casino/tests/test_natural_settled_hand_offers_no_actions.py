"""A hand settled by a dealer natural is finished: it offers no actions.

The natural settles the hand and stores its result, but it set no status, so the hand read as still open and the state
offered hit, stand, double, split and surrender on a settled round.
"""

from casino.services import game as game_mod


def test_a_hand_with_a_dealer_natural_result_offers_no_actions():
    flags = game_mod.hand_flags(cards=["KH", "5C"], status=None, split_count=0, surrender_allowed=True,
                                result="loss")
    assert not any(flags.values())


def test_a_hand_with_no_result_and_no_status_is_still_open():
    flags = game_mod.hand_flags(cards=["KH", "5C"], status=None, split_count=0, surrender_allowed=True)
    assert flags["can_hit"] and flags["can_stand"]
