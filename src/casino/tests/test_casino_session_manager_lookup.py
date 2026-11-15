"""CasinoSessionManager finds the sessions a moniker is bound to, as bed's SessionRegistry does.

The per-seat send asks the session registry for a player's sessions. Casino's own manager runs standalone
and under bed, so it needs the same method, returning ids in the same form (strings) bed does.
"""

from casino.api.handler import CasinoSessionManager


def test_sessions_for_moniker_lists_each_session_bound_to_it():
    mgr = CasinoSessionManager()
    mgr.register_session(1, "alice")
    mgr.register_session(2, "alice")
    mgr.register_session(3, "bob")
    assert sorted(mgr.sessions_for_moniker("alice")) == ["1", "2"]


def test_sessions_for_moniker_is_empty_for_an_unbound_moniker():
    mgr = CasinoSessionManager()
    mgr.register_session(1, "alice")
    assert mgr.sessions_for_moniker("nobody") == []


def test_an_unregistered_session_is_no_longer_listed():
    mgr = CasinoSessionManager()
    mgr.register_session(1, "alice")
    mgr.unregister_session(1)
    assert mgr.sessions_for_moniker("alice") == []
