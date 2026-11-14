"""Every refusal the GameService returns maps to exactly one casino code (blackjack adoption, slice 1).

The service still returns dicts; the adapter in casino.api.results turns a refusal into an ActionResult
with a code. The mapping is explicit: a refusal message that is not in the table raises, so a new
refusal cannot ship without a code.
"""

import re
from pathlib import Path

import pytest

from casino.api import results as res

pytestmark = pytest.mark.unit

SERVICE = Path(__file__).resolve().parents[1] / "services" / "game.py"

# Refusal message (exact text, as the service returns it) -> casino code.
MESSAGE_CODES = {
    "No active game": "no_active_game",
    "No hand found": "hand_not_found",
    "Hand not found": "hand_not_found",
    "No bet found": "no_bet_found",
    "No bet found for hand": "no_bet_found",
    "The round clock expired": "round_expired",
    "Table not found": "table_not_found",
    "Can only split with exactly 2 cards": "cannot_split",
    "Cards must have same rank to split": "cannot_split",
    "Maximum splits reached (4 hands max)": "cannot_split",
    "Insufficient funds to split": "insufficient_funds",
    "Can only double with exactly 2 cards": "cannot_double",
    "Insufficient funds to double": "insufficient_funds",
    "Surrender not allowed at this table": "cannot_surrender",
    "Can only surrender with exactly 2 cards": "cannot_surrender",
    "Cannot surrender after hitting": "cannot_surrender",
    "Insurance not available": "cannot_insure",
    "Insurance must be at least 1": "cannot_insure",
    "Insurance already taken": "cannot_insure",
}


def test_each_known_message_maps_to_its_code():
    for message, code in MESSAGE_CODES.items():
        r = res.refusal_from_message(message)
        assert r.ok is False and r.code == code and r.message == message, message


def test_unknown_refusal_message_raises():
    with pytest.raises(KeyError):
        res.refusal_from_message("Something nobody mapped")


def test_every_literal_refusal_in_the_service_is_mapped():
    text = SERVICE.read_text(encoding="utf-8")
    literals = set(re.findall(r'return \{"success": False, "message": "([^"]+)"\}', text))
    missing = sorted(m for m in literals if m not in MESSAGE_CODES)
    assert missing == [], missing



@pytest.mark.parametrize(
    "message,code",
    [
        ("Bet must be at least 5", "invalid_bet"),
        ("Bet cannot exceed 500", "invalid_bet"),
        ("Insurance cannot exceed 25", "cannot_insure"),
    ],
)
def test_dynamic_refusal_messages_map_by_pattern(message, code):
    r = res.refusal_from_message(message)
    assert r.code == code and r.message == message


def test_an_unrecognised_refusal_still_converts_for_the_reply():
    # A service error can be any text (str(e)). The reply must still be produced, with a generic code,
    # so a refused bet is never a crash in the handler.
    r = res.to_action_result({"success": False, "message": "database is busy"})
    assert r.ok is False and r.code == "service_error" and r.message == "database is busy"
