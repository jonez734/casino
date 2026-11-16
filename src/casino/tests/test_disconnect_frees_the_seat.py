"""A disconnect frees the seat the session held, as a leave does.

Before this, a player who disconnected without a leave kept their seat row, so the table still counted a
player who was gone. The disconnect now calls the same seat removal a leave uses (the table service's
leave_table), for the moniker that held the seat. A session that held no seat frees nothing.
"""

from types import SimpleNamespace

import pytest

from casino.api import handler as hmod


pytestmark = pytest.mark.unit


class _DomainTable:
    def __init__(self):
        self.left = []

    def leave_table(self, moniker, player):
        self.left.append((moniker, player))
        return {"success": True, "message": "Left table"}


class _Sessions:
    def __init__(self, table_moniker, moniker):
        self._table = table_moniker
        self._moniker = moniker

    def get_table_moniker(self, session_id):
        return self._table

    def get_moniker(self, session_id):
        return self._moniker

    def unregister_session(self, session_id):
        self.unregistered = session_id

    def sessions_for_moniker(self, moniker):
        return ["2"]  # only the session that is disconnecting


def _router(table_moniker, moniker, monkeypatch):
    monkeypatch.setattr(hmod, "channel_unsubscribe_all", lambda *a, **k: None)
    domain = _DomainTable()
    obj = hmod.MessageRouter.__new__(hmod.MessageRouter)
    obj.sessions = _Sessions(table_moniker, moniker)
    obj.table_service = SimpleNamespace(table_service=domain)
    obj.yahtzee_service_handler = SimpleNamespace(finalize_on_disconnect=lambda t: None)
    obj.tictactoe_service_handler = SimpleNamespace(finalize_on_disconnect=lambda t, m: None)
    obj.channel_state = None
    return obj, domain


def test_a_disconnect_seated_at_a_table_frees_that_seat(monkeypatch):
    obj, domain = _router("blackjack-jam", "jam", monkeypatch)
    obj.unregister_session(2)
    assert domain.left == [("blackjack-jam", "jam")]


def test_a_disconnect_not_seated_frees_nothing(monkeypatch):
    obj, domain = _router(None, "jam", monkeypatch)
    obj.unregister_session(2)
    assert domain.left == []


def test_closing_one_of_two_sockets_keeps_the_seat(monkeypatch):
    # A player on two sockets keeps the seat until the last one closes.
    obj, domain = _router("blackjack-jam", "jam", monkeypatch)
    obj.sessions = _TwoSessions("blackjack-jam", "jam", others=["7"])
    obj.unregister_session(2)
    assert domain.left == []


class _TwoSessions(_Sessions):
    def __init__(self, table_moniker, moniker, others):
        super().__init__(table_moniker, moniker)
        self._others = others

    def sessions_for_moniker(self, moniker):
        return list(self._others)
