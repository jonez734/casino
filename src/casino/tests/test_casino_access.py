"""
Unit tests for ``casino.access``.

Pins every (op, session, message) branch of the casino access
decision matrix. These are unit-only: no DB connection required.

Moved from ``bbsengine6/py/tests/test_casino_access.py`` to live
alongside the casino code that consumes the policy; the underlying
implementation under test now lives in ``casino.access`` (it was
moved out of ``bbsengine6.casino`` when that stub was dropped).
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest


sys.path.insert(0, "/home/opencode/data/work/bbsengine6/py/src")
sys.path.insert(0, "/home/opencode/data/work/casino/src")


from casino.access import access as casino_access  # noqa: E402


pytestmark = pytest.mark.unit


def _session(
    moniker: str | None = None,
    *,
    is_sysop: bool = False,
    table_moniker: str | None = None,
):
    """Build a session-like object with .moniker, .is_sysop, .table_moniker."""
    return SimpleNamespace(
        moniker=moniker,
        is_sysop=is_sysop,
        table_moniker=table_moniker,
    )


# ---------- module-load / unknown-op default ----------


def test_module_load_time_returns_true_without_session_kwarg():
    """bbsengine6.module.check calls access(op='run') at import time.

    We must allow the module to load unconditionally there; the
    per-op rules below only fire when ``session`` is passed.
    """
    assert casino_access(None, "run") is True
    assert casino_access(None, "anything") is True


def test_unknown_op_with_session_returns_false():
    """Unknown op verb falls through to the default deny."""
    s = _session("alice", is_sysop=True)
    assert casino_access(None, "no_such_op", session=s) is False


# ---------- list_tables ----------


def test_list_tables_allowed_without_session():
    s = None
    assert casino_access(None, "list_tables", session=s) is True


def test_list_tables_allowed_with_session():
    s = _session("alice")
    assert casino_access(None, "list_tables", session=s) is True


# ---------- create_table ----------


def test_create_table_denied_without_session():
    s = None
    assert casino_access(None, "create_table", session=s) is False


def test_create_table_allowed_for_authenticated():
    s = _session("alice")
    assert casino_access(None, "create_table", session=s) is True


def test_create_table_denied_for_empty_moniker_session():
    s = _session("")
    assert casino_access(None, "create_table", session=s) is False


# ---------- update_table / kick_player (owner-or-sysop) ----------


def test_update_table_owner_allowed():
    s = _session("alice")
    msg = {"table_moniker": "t1", "owner": "alice"}
    assert casino_access(None, "update_table", session=s, message=msg) is True


def test_update_table_non_owner_denied():
    s = _session("alice")
    msg = {"table_moniker": "t1", "owner": "bob"}
    assert casino_access(None, "update_table", session=s, message=msg) is False


def test_update_table_sysop_allowed_regardless_of_owner():
    s = _session("sysop", is_sysop=True)
    msg = {"table_moniker": "t1", "owner": "bob"}
    assert casino_access(None, "update_table", session=s, message=msg) is True


def test_update_table_denied_without_table_moniker():
    s = _session("alice")
    msg = {"owner": "alice"}
    assert casino_access(None, "update_table", session=s, message=msg) is False


def test_kick_player_owner_allowed():
    s = _session("alice")
    msg = {"table_moniker": "t1", "owner": "alice", "player_moniker": "bob"}
    assert casino_access(None, "kick_player", session=s, message=msg) is True


def test_kick_player_non_owner_denied():
    s = _session("alice")
    msg = {"table_moniker": "t1", "owner": "bob", "player_moniker": "carol"}
    assert casino_access(None, "kick_player", session=s, message=msg) is False


def test_kick_player_sysop_allowed():
    s = _session("sysop", is_sysop=True)
    msg = {"table_moniker": "t1", "owner": "alice", "player_moniker": "bob"}
    assert casino_access(None, "kick_player", session=s, message=msg) is True


# ---------- join_table / leave_table / watch_table / stop_watching ----------


def test_join_table_authenticated_allowed():
    s = _session("alice")
    msg = {"table_moniker": "t1"}
    assert casino_access(None, "join_table", session=s, message=msg) is True


def test_leave_table_authenticated_allowed():
    s = _session("alice", table_moniker="t1")
    msg = {"table_moniker": "t1"}
    assert casino_access(None, "leave_table", session=s, message=msg) is True


def test_watch_table_authenticated_allowed():
    s = _session("alice")
    assert casino_access(None, "watch_table", session=s) is True


def test_stop_watching_authenticated_allowed():
    s = _session("alice")
    assert casino_access(None, "stop_watching", session=s) is True


def test_join_table_empty_moniker_denied():
    s = _session("")
    assert casino_access(None, "join_table", session=s) is False


# ---------- bet / hit / stand / double / split / surrender (at table) ----------


@pytest.mark.parametrize(
    "op", ["bet", "hit", "stand", "double", "split", "surrender"]
)
def test_at_table_ops_allowed_when_seated_at_target(op):
    s = _session("alice", table_moniker="t1")
    msg = {"table_moniker": "t1"}
    assert casino_access(None, op, session=s, message=msg) is True


@pytest.mark.parametrize(
    "op", ["bet", "hit", "stand", "double", "split", "surrender"]
)
def test_at_table_ops_denied_when_not_seated(op):
    s = _session("alice", table_moniker=None)
    msg = {"table_moniker": "t1"}
    assert casino_access(None, op, session=s, message=msg) is False


@pytest.mark.parametrize(
    "op", ["bet", "hit", "stand", "double", "split", "surrender"]
)
def test_at_table_ops_denied_when_seated_at_wrong_table(op):
    s = _session("alice", table_moniker="t2")
    msg = {"table_moniker": "t1"}
    assert casino_access(None, op, session=s, message=msg) is False


@pytest.mark.parametrize(
    "op", ["bet", "hit", "stand", "double", "split", "surrender"]
)
def test_at_table_ops_denied_with_no_session(op):
    s = None
    msg = {"table_moniker": "t1"}
    assert casino_access(None, op, session=s, message=msg) is False


# ---------- chat / emote ----------


@pytest.mark.parametrize("op", ["chat_table", "chat_global", "emote"])
def test_chat_ops_allowed_for_authenticated(op):
    s = _session("alice")
    assert casino_access(None, op, session=s) is True


@pytest.mark.parametrize("op", ["chat_table", "chat_global", "emote"])
def test_chat_ops_denied_for_empty_moniker(op):
    s = _session("")
    assert casino_access(None, op, session=s) is False


@pytest.mark.parametrize("op", ["chat_table", "chat_global", "emote"])
def test_chat_ops_denied_with_no_session(op):
    s = None
    assert casino_access(None, op, session=s) is False


# ---------- slot_spin / slot_paytable (at table) ----------


def test_slot_spin_allowed_when_seated_at_target():
    s = _session("alice", table_moniker="t1")
    msg = {"table_moniker": "t1"}
    assert casino_access(None, "slot_spin", session=s, message=msg) is True


def test_slot_spin_denied_when_not_seated():
    s = _session("alice", table_moniker=None)
    msg = {"table_moniker": "t1"}
    assert casino_access(None, "slot_spin", session=s, message=msg) is False


def test_slot_paytable_allowed_when_seated():
    s = _session("alice", table_moniker="t1")
    msg = {"table_moniker": "t1"}
    assert casino_access(None, "slot_paytable", session=s, message=msg) is True


def test_slot_paytable_denied_when_not_seated():
    s = _session("alice", table_moniker=None)
    msg = {"table_moniker": "t1"}
    assert casino_access(None, "slot_paytable", session=s, message=msg) is False


# ---------- slot_history (self or sysop) ----------


def test_slot_history_self_allowed():
    s = _session("alice")
    msg = {"moniker": "alice"}
    assert casino_access(None, "slot_history", session=s, message=msg) is True


def test_slot_history_other_denied():
    s = _session("alice")
    msg = {"moniker": "bob"}
    assert casino_access(None, "slot_history", session=s, message=msg) is False


def test_slot_history_sysop_allowed_for_other():
    s = _session("sysop", is_sysop=True)
    msg = {"moniker": "alice"}
    assert casino_access(None, "slot_history", session=s, message=msg) is True


def test_slot_history_empty_target_denied():
    s = _session("alice")
    msg = {"moniker": ""}
    assert casino_access(None, "slot_history", session=s, message=msg) is False


# ---------- yahtzee / tictactoe ----------


@pytest.mark.parametrize(
    "op",
    [
        "yahtzee_quick_play",
        "yahtzee_roll",
        "yahtzee_reroll",
        "yahtzee_score",
        "tictactoe_quick_play",
        "tictactoe_move",
        "tictactoe_resign",
        "tictactoe_join",
    ],
)
def test_yahtzee_tictactoe_ops_denied_with_no_session(op):
    s = None
    msg = {"table_moniker": "t1"}
    assert casino_access(None, op, session=s, message=msg) is False


@pytest.mark.parametrize(
    "op",
    [
        "yahtzee_quick_play",
        "tictactoe_quick_play",
    ],
)
def test_quick_play_allowed_for_authenticated(op):
    """quick_play creates a fresh table; no seat-at check."""
    s = _session("alice", table_moniker=None)
    msg = {"table_moniker": "t-new"}
    assert casino_access(None, op, session=s, message=msg) is True


@pytest.mark.parametrize(
    "op",
    [
        "yahtzee_roll",
        "yahtzee_reroll",
        "yahtzee_score",
        "tictactoe_move",
        "tictactoe_resign",
        "tictactoe_join",
    ],
)
def test_yahtzee_tictactoe_seated_ops_allowed_when_seated(op):
    s = _session("alice", table_moniker="t1")
    msg = {"table_moniker": "t1"}
    assert casino_access(None, op, session=s, message=msg) is True


@pytest.mark.parametrize(
    "op",
    [
        "yahtzee_roll",
        "yahtzee_reroll",
        "yahtzee_score",
        "tictactoe_move",
        "tictactoe_resign",
        "tictactoe_join",
    ],
)
def test_yahtzee_tictactoe_seated_ops_denied_when_not_seated(op):
    s = _session("alice", table_moniker=None)
    msg = {"table_moniker": "t1"}
    assert casino_access(None, op, session=s, message=msg) is False


# ---------- claim-derived override ----------


def test_claim_sysop_bypasses_ownership_gate():
    """Claim-derived is_sysop wins over session.is_sysop=False."""
    s = _session("alice", is_sysop=False)
    msg = {
        "table_moniker": "t1",
        "owner": "bob",
        "claims": {"moniker": "sysop", "is_sysop": True},
    }
    assert casino_access(None, "update_table", session=s, message=msg) is True


def test_claim_moniker_used_for_self_history():
    """Claim-derived moniker wins for slot_history self-check."""
    s = _session("alice", is_sysop=False)
    msg = {"moniker": "bob", "claims": {"moniker": "bob"}}
    assert casino_access(None, "slot_history", session=s, message=msg) is True


def test_claim_is_sysop_false_overrides_session_true():
    """A claim that explicitly says is_sysop=False wins over a session
    that says True (defence in depth against a forged session)."""
    s = _session("alice", is_sysop=True)
    msg = {
        "table_moniker": "t1",
        "owner": "bob",
        "claims": {"moniker": "alice", "is_sysop": False},
    }
    assert casino_access(None, "update_table", session=s, message=msg) is False


def test_no_claim_falls_back_to_session_attributes():
    """Without claims, session attributes are used."""
    s = _session("alice", is_sysop=False)
    msg = {"table_moniker": "t1", "owner": "alice"}
    assert casino_access(None, "update_table", session=s, message=msg) is True


# ---------- empty / malformed claims ----------


def test_empty_claims_falls_back_to_session():
    s = _session("alice")
    msg = {"table_moniker": "t1", "owner": "alice", "claims": {}}
    assert casino_access(None, "update_table", session=s, message=msg) is True


def test_malformed_claims_falls_back_to_session():
    """Non-dict claims are treated as empty by _get_claims."""
    s = _session("alice")
    msg = {"table_moniker": "t1", "owner": "alice", "claims": "not-a-dict"}
    assert casino_access(None, "update_table", session=s, message=msg) is True


# ---------- case-insensitive moniker comparison ----------


def test_owner_check_is_case_insensitive():
    s = _session("Alice")
    msg = {"table_moniker": "t1", "owner": "alice"}
    assert casino_access(None, "update_table", session=s, message=msg) is True


def test_slot_history_self_check_is_case_insensitive():
    s = _session("Alice")
    msg = {"moniker": "ALICE"}
    assert casino_access(None, "slot_history", session=s, message=msg) is True
