"""Hosted init: casino uses the bedsession's pool and identity instead of its own.

When letteredolive starts casino, the shell already owns the connection pool, has started
the session, and knows the signed-in member. The door loop must:

  - use the bedsession's pool, and not close it (the shell closes it on exit);
  - not start a second session;
  - take the member from the bedsession's identity.

Standalone (no bedsession) keeps its own pool, session start, and member lookup.
"""

import importlib
from argparse import Namespace
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest

from casino import host

door = importlib.import_module("casino.main")


pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _standalone_after():
    host.unregister_menu()
    yield
    host.unregister_menu()


def _args():
    return Namespace(debug=False, databasename="zoid6", databasehost="h", databaseport=5432,
                     databaseuser="u", databasepassword=None)


class _ClosingPool:
    """A stand-in pool that records whether it was closed."""

    def __init__(self):
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.closed = True
        return False


def _player():
    p = MagicMock()
    p.moniker = "alice"
    p.connected = False
    p.current_table_moniker = None
    return p


def _bedsession(pool, identity="alice"):
    """A bedsession-shaped object: the pool, the identity, and a menu that quits at once."""
    return type("BS", (), {
        "pool": pool,
        "identity": identity,
        "choose": staticmethod(lambda prompt, registry, default="", help=None: "q"),
    })()


def _run(bedsession=None):
    """Run the door loop once with collaborators stubbed. Returns the stubs for assertions."""
    with ExitStack() as stack:
        getpool = stack.enter_context(patch.object(door.database, "getpool"))
        start = stack.enter_context(patch.object(door.session, "start", return_value=True))
        getmoniker = stack.enter_context(
            patch.object(door.member, "getcurrentmoniker", return_value="alice"))
        stack.enter_context(patch.object(door.lib, "setbottombar"))
        stack.enter_context(patch.object(door.lib, "_unregister_casino_fragments"))
        stack.enter_context(patch.object(door.lib, "_clear_bottombar"))
        stack.enter_context(patch.object(door.lib, "CasinoPlayer", return_value=_player()))
        stack.enter_context(patch.object(door.lib, "runmodule", return_value=True))
        stack.enter_context(patch.object(door.io, "echo"))
        stack.enter_context(patch.object(door.auth, "init_remote_client_screen"))
        stack.enter_context(patch.object(door.auth, "cleanup_remote_client_screen"))
        stack.enter_context(patch.object(door.auth, "disconnect"))
        stack.enter_context(patch.object(door.io, "inputchoice", return_value="Q"))
        if bedsession is None:
            pool_cm = _ClosingPool()
            getpool.return_value = pool_cm
        else:
            pool_cm = bedsession.pool
            getpool.return_value = _ClosingPool()
        door.main(_args(), **({} if bedsession is None else {"bedsession": bedsession}))
    return {"getpool": getpool, "start": start, "getmoniker": getmoniker, "pool": pool_cm}


def test_hosted_uses_the_bedsession_pool_and_never_opens_its_own():
    shell_pool = _ClosingPool()
    out = _run(_bedsession(shell_pool))
    out["getpool"].assert_not_called()


def test_hosted_does_not_close_the_shell_pool():
    shell_pool = _ClosingPool()
    _run(_bedsession(shell_pool))
    assert shell_pool.closed is False


def test_hosted_does_not_start_a_second_session():
    out = _run(_bedsession(_ClosingPool()))
    out["start"].assert_not_called()


def test_hosted_takes_the_member_from_the_bedsession_identity():
    out = _run(_bedsession(_ClosingPool(), identity="bob"))
    out["getmoniker"].assert_not_called()


def test_hosted_with_empty_identity_is_not_a_member():
    """An empty identity means no member. It must stop the run, not create a blank player."""
    player_cls = MagicMock()
    with patch.object(door.lib, "CasinoPlayer", player_cls):
        _run(_bedsession(_ClosingPool(), identity=""))
    player_cls.assert_not_called()


def test_standalone_opens_its_own_pool_and_closes_it():
    out = _run(None)
    out["getpool"].assert_called_once()
    assert out["pool"].closed is True


def test_standalone_starts_the_session_and_looks_up_the_member():
    out = _run(None)
    out["start"].assert_called_once()
    out["getmoniker"].assert_called_once()
