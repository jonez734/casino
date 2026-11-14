"""The adapter reproduces the service's dict exactly on the wire (blackjack adoption, slice 1).

For each result shape the service returns, to_wire(to_action_result(d)) must equal d. This is the
golden check: any later slice that changes how results are built must keep it green.
"""

import pytest

from casino.api import results as res

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "service_result",
    [
        {"success": True, "hand_id": 3, "cards": ["10H", "7D"], "total": 17, "busted": False},
        {"success": True, "outcomes": [], "dealer_total": 17, "dealer_cards": ["10H", "7D"]},
        {"success": True},
        {"success": False, "message": "No active game"},
        {"success": False, "message": "Insufficient funds to double", "required": 10},
        {"success": False, "message": "The round clock expired"},
    ],
)
def test_wire_dict_round_trips_exactly(service_result):
    assert res.to_wire(res.to_action_result(service_result)) == service_result


def test_refusal_carries_its_code_on_the_framework_type():
    r = res.to_action_result({"success": False, "message": "No active game"})
    assert r.ok is False and r.code == "no_active_game"


def test_success_is_code_ok():
    r = res.to_action_result({"success": True, "hand_id": 1})
    assert r.ok is True and r.code == "ok" and dict(r.data) == {"hand_id": 1}


def test_unmapped_refusal_fails_the_conversion():
    with pytest.raises(KeyError):
        res.to_action_result({"success": False, "message": "never mapped"})
