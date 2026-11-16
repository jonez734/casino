"""Adapter from the GameService's dict results to bbsengine6 ActionResult, and back to the wire dict.

The service still returns dicts (``{"success": ..., "message": ...}``). This module is the seam between
that and the framework type: a refusal becomes an ActionResult with a code from the explicit table
below, and the handler maps the result back to the wire dict it sends today. A refusal message that is
not in the table raises KeyError, so a new refusal cannot ship without a code.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

from bbsengine6.seam.results import ActionResult, refusal, register_code, success

# Refusal message (exact text the service returns) -> casino code.
REFUSAL_CODES: dict[str, str] = {
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
    "The deal failed; your bet was returned.": "deal_failed",
    "Your hand is finished.": "hand_finished",
    "You cannot bet while your hand is still in play.": "hand_open",
}


# Refusals whose text contains a value (a limit, a cap). Matched by pattern; the first match wins.
REFUSAL_PATTERNS: list[tuple[str, str]] = [
    (r"^Bet must be at least \d+$", "invalid_bet"),
    (r"^Bet cannot exceed \d+$", "invalid_bet"),
    (r"^Insurance cannot exceed \d+$", "cannot_insure"),
]

# A refusal the adapter does not recognise (an exception's text, for example) gets this generic code,
# so the reply is still produced rather than the handler crashing.
UNRECOGNISED_CODE = "service_error"



def code_for_message(message: str) -> str:
    """The casino code for a refusal message: the exact table, then the patterns, else UNRECOGNISED_CODE."""
    if message in REFUSAL_CODES:
        return REFUSAL_CODES[message]
    for pattern, code in REFUSAL_PATTERNS:
        if re.match(pattern, message):
            return code
    return UNRECOGNISED_CODE


def refusal_from_message(message: str) -> ActionResult:
    """The ActionResult for a refusal message whose code is known. Raises KeyError for an unknown text,
    so the table cannot silently miss a message the service really returns."""
    if message not in REFUSAL_CODES and not any(re.match(p, message) for p, _ in REFUSAL_PATTERNS):
        raise KeyError(message)
    return refusal(code_for_message(message), message)


def to_action_result(result: Mapping[str, Any]) -> ActionResult:
    """Convert a service dict to an ActionResult. The dict's other keys become ``data``."""
    data = {k: v for k, v in result.items() if k not in ("success", "message")}
    if result.get("success"):
        return success(data)
    return refusal(code_for_message(result["message"]), result["message"], data)


def to_wire(result: ActionResult) -> dict[str, Any]:
    """The dict the client receives, with the keys it has always had.

    A refusal always carries ``message``. A success carries it only when it had one, as the service
    returns it, so the round trip is exact.
    """
    body: dict[str, Any] = {"success": result.ok}
    if not result.ok or result.message:
        body["message"] = result.message
    body.update(result.data)
    return body


# Casino's blackjack refusal codes, registered with the seam so it accepts them. Table, bet, and money
# codes are casino's too; they are already in api/messages.py.
# UNRECOGNISED_CODE is generic (service_error) and already known to the seam, so it is not registered.
for _code in sorted(set(REFUSAL_CODES.values()) | {c for _, c in REFUSAL_PATTERNS}):
    register_code(_code)
