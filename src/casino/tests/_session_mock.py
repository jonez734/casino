# casino/tests/_session_mock.py
# Shared mock-state helpers for casino handler tests.
#
# Casino's pre-migration test suite stubbed the session manager via
# ``sessions.get_moniker.return_value = "alice"``. After the migration
# to the bank-style ``casino.access()`` pipeline, the
# per-op ``_check_access`` looks the session up via
# ``sessions.get_by_websocket(str(ws.id))`` and expects an
# attribute-style state object (``bed.api.session.SessionState`` or
# a duck-typed mirror). The MagicMock the tests pass as ``sessions``
# has to return such an object.
#
# The bridge below reads ``sessions.get_moniker(...)`` /
# ``sessions.get_table_moniker(...)`` (the LEGACY contract still
# stubbed in the tests) and synthesizes a state object so the
# handler can run end-to-end without re-writing every test's
# fixture.

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Optional


def make_mock_state(
    *,
    moniker: Optional[str] = None,
    is_sysop: bool = False,
    table_moniker: Optional[str] = None,
    spectator_of: Optional[set] = None,
    session_id: str = "s1",
    websocket_id: str = "ws-1",
) -> SimpleNamespace:
    """Build a ``SimpleNamespace`` that satisfies ``casino.access``'s
    attribute reads (``state.moniker`` / ``state.is_sysop`` /
    ``state.table_moniker``) and the casino handler's
    ``getattr(state, "...")`` probes.
    """
    return SimpleNamespace(
        session_id=session_id,
        websocket_id=websocket_id,
        moniker=moniker,
        is_sysop=bool(is_sysop),
        table_moniker=table_moniker,
        spectator_of=set(spectator_of) if spectator_of else set(),
        auth_service_token=None,
        loginid=None,
        balance=None,
    )


def bridge_sessions_mock(sessions: Any) -> Any:
    """Wire a MagicMock ``sessions`` so legacy stubs continue to drive
    the handler's lookup.

    Returns the same ``sessions`` after attaching a
    ``get_by_websocket`` stub that consults the legacy
    ``get_moniker`` / ``get_table_moniker`` stubs and returns a
    state-like object. ``is_sysop`` is read off the session if the
    test set it via ``sessions.get_is_sysop.return_value``; otherwise
    defaults to False.
    """
    def _resolve(ws_id: Any) -> Optional[SimpleNamespace]:
        try:
            sid = int(ws_id)
        except Exception:
            sid = ws_id
        moniker = None
        try:
            moniker = sessions.get_moniker(sid)
        except Exception:
            try:
                moniker = sessions.get_moniker()
            except Exception:
                moniker = None
        if not moniker:
            return None
        try:
            table_moniker = sessions.get_table_moniker(sid)
        except Exception:
            table_moniker = None
        try:
            is_sysop = bool(sessions.get_is_sysop(sid))
        except Exception:
            is_sysop = False
        return make_mock_state(
            moniker=moniker,
            is_sysop=is_sysop,
            table_moniker=table_moniker,
        )

    sessions.get_by_websocket.side_effect = _resolve
    sessions.get_session.return_value = None
    return sessions


def make_sessions_mock(
    *,
    moniker: Optional[str] = None,
    is_sysop: bool = False,
    table_moniker: Optional[str] = None,
) -> Any:
    """Build a MagicMock ``sessions`` pre-wired with state stubs.

    ``moniker=None`` simulates an unauthenticated websocket (handler
    returns ``not_authenticated``). ``is_sysop=True`` lets the test
    drive sysop-only paths. ``table_moniker`` is the table the
    session is seated at, used by gameplay-op tests.

    The returned mock dynamically resolves ``get_by_websocket`` from
    the test-side ``get_moniker`` / ``get_table_moniker`` / ``get_is_sysop``
    stubs so legacy tests can flip ``sessions.get_moniker.return_value``
    to ``None`` mid-test and the handler sees an unauthenticated
    session without re-stubbing ``get_by_websocket``.
    """
    from unittest.mock import MagicMock

    sessions = MagicMock()
    sessions.get_moniker.return_value = moniker
    sessions.get_table_moniker.return_value = table_moniker
    sessions.get_is_sysop.return_value = bool(is_sysop)

    def _resolve(ws_id: Any) -> Optional[SimpleNamespace]:
        try:
            sid = int(ws_id)
        except Exception:
            sid = ws_id
        try:
            m = sessions.get_moniker(sid)
            if m is None:
                m = sessions.get_moniker()
        except Exception:
            m = sessions.get_moniker()
        if not m:
            return None
        try:
            tm = sessions.get_table_moniker(sid)
            if tm is None:
                tm = sessions.get_table_moniker()
        except Exception:
            tm = sessions.get_table_moniker()
        try:
            sop = bool(sessions.get_is_sysop(sid))
            if not sop:
                sop = bool(sessions.get_is_sysop())
        except Exception:
            sop = bool(sessions.get_is_sysop())
        return make_mock_state(moniker=m, is_sysop=sop, table_moniker=tm)

    sessions.get_by_websocket.side_effect = _resolve
    sessions.get_session.return_value = None
    return sessions
