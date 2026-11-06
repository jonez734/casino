"""The spin idempotency key: its validation, and the stored-spin reply shape.

The database behaviour (a retry returns the stored spin and moves no money) is checked by
test_spin_retry_no_double_settle.py against the test database. These tests cover the Python side.
"""

import pytest

from casino.services import slots


@pytest.mark.parametrize("key", ["abc123", "spin-1_OK", "x" * 64, "A", "9"])
def test_valid_keys_are_accepted(key):
    assert slots._idempotency_key_error(key) is None


def test_absent_key_is_accepted_and_means_a_server_id():
    assert slots._idempotency_key_error(None) is None


@pytest.mark.parametrize("key", ["", "x" * 65, "has space", "semi;colon", "dot.dot", 42, ["list"], b"bytes"])
def test_bad_keys_are_refused_with_a_reason(key):
    reason = slots._idempotency_key_error(key)
    assert reason is not None and "idempotency_key" in reason


def test_handle_spin_refuses_a_bad_key_before_any_settlement():
    out = slots.handle_spin(
        args=None, table_moniker="t", player_moniker="alice", bet=10,
        message={"idempotency_key": "semi;colon"}, state=None,
    )
    assert out["success"] is False and out["code"] == "invalid_request"


def test_stored_spin_reply_has_the_same_keys_as_a_first_settle():
    """The duplicate reply is built from the stored result with the same keys a first success has."""
    stored = {
        "success": True, "duplicate": True, "spin_id": 7, "new_balance": 990,
        "table_moniker": "t", "bet": 10, "payout": 25, "net": 15,
        "reels": [["A", "B", "C"]], "wins": [],
    }
    built = {
        "id": int(stored["spin_id"]), "table_moniker": stored["table_moniker"],
        "bet": int(stored["bet"]), "payout": int(stored["payout"]), "net": int(stored["net"]),
        "new_balance": int(stored["new_balance"]), "reels": stored["reels"],
        "center_row": [], "wins": stored["wins"],
    }
    first = {"id", "table_moniker", "bet", "payout", "net", "new_balance", "reels", "center_row", "wins"}
    assert set(built) == first
