"""CasinoSessionManager's lookups return the connection ids the transport routes on, as bed's registry does.

A session is keyed by an integer here, but the transport routes a message by the connection's websocket id (a
UUID). The manager records that id when the session is registered, and its lookups return it.
"""

import uuid

import pytest

from casino.api.handler import CasinoSessionManager


pytestmark = pytest.mark.unit


def test_sessions_for_moniker_returns_the_connection_ids():
    mgr = CasinoSessionManager()
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    mgr.register_session(1, "alice", connection_id=a)
    mgr.register_session(2, "alice", connection_id=b)
    mgr.register_session(3, "bob", connection_id=str(uuid.uuid4()))
    assert sorted(mgr.sessions_for_moniker("alice")) == sorted([a, b])


def test_sessions_for_moniker_is_empty_for_an_unbound_moniker():
    mgr = CasinoSessionManager()
    mgr.register_session(1, "alice", connection_id=str(uuid.uuid4()))
    assert mgr.sessions_for_moniker("nobody") == []


def test_an_unregistered_session_is_no_longer_listed():
    mgr = CasinoSessionManager()
    mgr.register_session(1, "alice", connection_id=str(uuid.uuid4()))
    mgr.unregister_session(1)
    assert mgr.sessions_for_moniker("alice") == []


def test_get_table_observers_returns_the_watchers_connection_ids():
    mgr = CasinoSessionManager()
    watcher = str(uuid.uuid4())
    mgr.register_session(9, "carol", connection_id=watcher)
    mgr.add_spectator("blackjack-a", 9)
    assert mgr.get_table_observers("blackjack-a") == {watcher}
