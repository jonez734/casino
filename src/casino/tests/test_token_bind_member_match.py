"""A valid wire token is bound to a password session only when it belongs to that session's member.

Regression for a review finding: any token that validated was bound, so a member could spend
another member's money with that member's token.
"""

from types import SimpleNamespace
from unittest.mock import patch

from casino.api import _auth


def _state(moniker):
    return SimpleNamespace(moniker=moniker, auth_service_token=None, session_id="s", websocket_id="w")


def _run(state, claims, token="tok"):
    """Call the bind path with a session already bound to ``state`` and a validating token."""
    msg = {"type": "slot_spin", "token": token}
    with patch.object(_auth, "_get_session_state", return_value=state), \
         patch.object(_auth, "_validate_wire_token", return_value=(claims, None)):
        result, err = _auth._get_or_bind_session_for(object(), object(), msg)
    return result, err, msg


def test_own_token_is_bound():
    st = _state("alice")
    result, err, msg = _run(st, {"moniker": "alice"})
    assert err is None
    assert st.auth_service_token == "tok"
    assert msg["claims"] == {"moniker": "alice"}


def test_another_members_valid_token_is_not_bound():
    st = _state("alice")
    result, err, msg = _run(st, {"moniker": "bob"})
    assert err is None  # the session itself is still returned; the token is what is refused
    assert st.auth_service_token is None
    assert "claims" not in msg


def test_existing_token_is_not_replaced():
    st = _state("alice")
    st.auth_service_token = "already-bound"
    _run(st, {"moniker": "alice"}, token="new")
    assert st.auth_service_token == "already-bound"


def test_invalid_token_is_not_bound():
    st = _state("alice")
    msg = {"type": "slot_spin", "token": "bad"}
    with patch.object(_auth, "_get_session_state", return_value=st), \
         patch.object(_auth, "_validate_wire_token", return_value=(None, {"code": "token_invalid"})):
        _auth._get_or_bind_session_for(object(), object(), msg)
    assert st.auth_service_token is None
