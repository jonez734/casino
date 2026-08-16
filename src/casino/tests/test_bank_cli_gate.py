#!/usr/bin/env python3
"""Tests for the casino bank CLI local authorization gate.

The casino bank subcommands (``bank_balance``, ``bank_add``, etc.)
gate locally through ``bbsengine6.bank.access`` -- the same module-
level policy ``bed tools bank`` uses -- so the local CLI agrees with
the server's claim-derived authorization. The ``_check_access`` helper
in :mod:`casino.commands.bank.lib` builds a SessionState-like stub from
``args._session_*`` claim-derived attributes and lets the policy
decide.

These tests cover the helper directly (mocking out the casino client)
so we can drive the success / failure paths deterministically.
"""

from __future__ import annotations

import argparse
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, "/home/opencode/data/work/casino/src")
sys.path.insert(0, "/home/opencode/data/work/bbsengine6/py/src")


# ---------------------------------------------------------------------
# Helpers


def _make_args(**overrides) -> argparse.Namespace:
    args = argparse.Namespace()
    args.token_file = None
    args.moniker = ""
    args.sysop = False
    args._session_moniker = ""
    args._session_is_sysop = False
    for k, v in overrides.items():
        setattr(args, k, v)
    return args


def _make_client(moniker: str = "alice", is_sysop: bool = False) -> MagicMock:
    c = MagicMock()
    c.authenticated = True
    c.moniker = moniker
    c.is_sysop = is_sysop
    c.balance = 0
    c._loop = MagicMock()
    c._loop.run_until_complete = MagicMock(return_value=None)
    c.cmd_bank_balance = MagicMock()
    c.cmd_bank_add = MagicMock()
    c.cmd_bank_remove = MagicMock()
    c.cmd_bank_transfer = MagicMock()
    c.cmd_bank_approve = MagicMock()
    c.cmd_bank_reject = MagicMock()
    c.cmd_bank_pending = MagicMock()
    c.cmd_bank_history = MagicMock()
    c.cmd_bank_list_all = MagicMock()
    return c


# ---------------------------------------------------------------------
# _make_session / _resolve_actor_moniker


def test_make_session_prefers_explicit_argument():
    """Explicit moniker argument wins over args.moniker and
    args._session_moniker.
    """
    from casino.commands.bank.lib import _make_session

    args = _make_args(moniker="args-moniker", _session_moniker="claims-moniker")
    sess = _make_session(args, moniker="explicit-moniker")
    assert sess.moniker == "explicit-moniker"


def test_make_session_falls_back_to_session_moniker():
    """When no explicit moniker is passed, ``_session_moniker``
    (claim-derived) wins over ``args.moniker`` because the token is
    the cryptographic source of truth.
    """
    from casino.commands.bank.lib import _make_session

    args = _make_args(moniker="args-moniker", _session_moniker="claims-moniker")
    sess = _make_session(args)
    assert sess.moniker == "claims-moniker"


def test_make_session_falls_back_to_args_moniker():
    """When no session-moniker is set, ``args.moniker`` is the last
    resort so direct-mode callers that didn't pre-resolve a moniker
    still get a valid actor.
    """
    from casino.commands.bank.lib import _make_session

    args = _make_args(moniker="args-moniker")
    sess = _make_session(args)
    assert sess.moniker == "args-moniker"


def test_make_session_is_sysop_precedence():
    """``args.sysop`` flag wins over ``args._session_is_sysop``.
    """
    from casino.commands.bank.lib import _make_session

    args = _make_args(sysop=True, _session_is_sysop=False)
    assert _make_session(args).is_sysop is True
    args = _make_args(sysop=False, _session_is_sysop=True)
    assert _make_session(args).is_sysop is True
    args = _make_args(sysop=False, _session_is_sysop=False)
    assert _make_session(args).is_sysop is False


def test_resolve_actor_moniker_prefers_session_moniker():
    """``args._session_moniker`` wins over fallback and args.moniker.
    """
    from casino.commands.bank.lib import _resolve_actor_moniker

    args = _make_args(
        moniker="args-moniker", _session_moniker="claims-moniker"
    )
    assert _resolve_actor_moniker(args, fallback="fallback-moniker") == "claims-moniker"


def test_resolve_actor_moniker_strips_whitespace():
    """Whitespace is stripped so a leading newline from the token
    file does not leak into the actor moniker.
    """
    from casino.commands.bank.lib import _resolve_actor_moniker

    args = _make_args(_session_moniker="  alice\n")
    assert _resolve_actor_moniker(args) == "alice"


# ---------------------------------------------------------------------
# _check_access


def test_check_access_unauthenticated_denies():
    """When no actor moniker is resolvable, the subcommand is denied
    unconditionally.
    """
    from casino.commands.bank.lib import _check_access

    args = _make_args()  # no moniker anywhere
    allowed = _check_access(args, "balance")
    assert allowed is False


def test_check_access_unauthenticated_does_not_call_policy():
    """The session-bound gate is checked BEFORE the policy is called
    so unauthenticated callers never reach ``bbsengine6.bank.access``.
    """
    from casino.commands.bank import lib

    args = _make_args()
    with patch.object(lib, "_bank_access") as policy:
        lib._check_access(args, "balance")
        policy.assert_not_called()


def test_check_access_passes_message_fields():
    """``_check_access`` puts the keyword arguments into the message
    dict the bank policy reads.
    """
    from casino.commands.bank import lib

    args = _make_args(_session_moniker="alice")
    captured = {}

    def fake_policy(args_, op, /, **kwargs):
        captured["op"] = op
        captured["session"] = kwargs.get("session")
        captured["message"] = kwargs.get("message")
        return True

    with patch.object(lib, "_bank_access", side_effect=fake_policy):
        ok = lib._check_access(
            args,
            "balance",
            session_moniker="alice",
            moniker="table-x",
        )

    assert ok is True
    assert captured["op"] == "balance"
    assert captured["session"].moniker == "alice"
    assert captured["message"] == {"moniker": "table-x"}


def test_check_access_drops_none_message_fields():
    """``None`` message fields are dropped so callers can pass
    optional values without polluting the policy's message dict.
    """
    from casino.commands.bank import lib

    args = _make_args(_session_moniker="alice")
    captured = {}

    def fake_policy(args_, op, /, **kwargs):
        captured["message"] = kwargs.get("message")
        return True

    with patch.object(lib, "_bank_access", side_effect=fake_policy):
        lib._check_access(
            args, "balance", session_moniker="alice", moniker="t", optional=None
        )

    assert "optional" not in captured["message"]


# ---------------------------------------------------------------------
# Subcommand handlers (smoke test)


def test_bank_balance_denies_when_unauthenticated():
    """The handler refuses to send the wire message when the actor
    has no moniker. No ``cmd_bank_balance`` call.

    The actor is read from the casino client's ``.moniker`` (which
    was set after a successful connect / token-file bind) and
    resolved through :func:`_resolve_actor_moniker`. With neither
    ``args._session_moniker`` nor a client moniker, the actor is
    empty and the policy denies.
    """
    from casino.commands.bank import lib

    args = _make_args()  # no actor
    client = _make_client(moniker="")  # not logged in
    with patch.object(lib, "_bank_access", return_value=True) as policy:
        ok = lib.bank_balance(args, client=client)
    assert ok is False
    client.cmd_bank_balance.assert_not_called()
    policy.assert_not_called()


def test_bank_balance_calls_cmd_when_authorized():
    """When the actor is authenticated, the handler runs the
    underlying ``cmd_bank_balance`` (the actual wire send).
    """
    from casino.commands.bank import lib

    args = _make_args(_session_moniker="alice")
    client = _make_client(moniker="alice")
    with patch.object(lib, "_bank_access", return_value=True):
        ok = lib.bank_balance(args, client=client)
    assert ok is True
    client.cmd_bank_balance.assert_called_once()


def test_bank_add_runs_cmd_when_authorized():
    from casino.commands.bank import lib

    args = _make_args(_session_moniker="alice")
    client = _make_client(moniker="alice")
    with patch.object(lib, "_bank_access", return_value=True):
        ok = lib.bank_add(args, client=client)
    assert ok is True
    client.cmd_bank_add.assert_called_once()


def test_bank_remove_runs_cmd_when_authorized():
    from casino.commands.bank import lib

    args = _make_args(_session_moniker="alice")
    client = _make_client(moniker="alice")
    with patch.object(lib, "_bank_access", return_value=True):
        ok = lib.bank_remove(args, client=client)
    assert ok is True
    client.cmd_bank_remove.assert_called_once()


def test_bank_transfer_runs_cmd_when_authorized():
    from casino.commands.bank import lib

    args = _make_args(_session_moniker="alice")
    client = _make_client(moniker="alice")
    with patch.object(lib, "_bank_access", return_value=True):
        ok = lib.bank_transfer(args, client=client)
    assert ok is True
    client.cmd_bank_transfer.assert_called_once()


def test_bank_approve_runs_cmd_when_authorized():
    from casino.commands.bank import lib

    args = _make_args(_session_moniker="alice")
    client = _make_client(moniker="alice")
    with patch.object(lib, "_bank_access", return_value=True):
        ok = lib.bank_approve(args, client=client)
    assert ok is True
    client.cmd_bank_approve.assert_called_once()


def test_bank_reject_runs_cmd_when_authorized():
    from casino.commands.bank import lib

    args = _make_args(_session_moniker="alice")
    client = _make_client(moniker="alice")
    with patch.object(lib, "_bank_access", return_value=True):
        ok = lib.bank_reject(args, client=client)
    assert ok is True
    client.cmd_bank_reject.assert_called_once()


def test_bank_pending_runs_cmd_when_authorized():
    from casino.commands.bank import lib

    args = _make_args(_session_moniker="alice")
    client = _make_client(moniker="alice")
    with patch.object(lib, "_bank_access", return_value=True):
        ok = lib.bank_pending(args, client=client)
    assert ok is True
    client.cmd_bank_pending.assert_called_once()


def test_bank_history_runs_cmd_when_authorized():
    from casino.commands.bank import lib

    args = _make_args(_session_moniker="alice")
    client = _make_client(moniker="alice")
    with patch.object(lib, "_bank_access", return_value=True):
        ok = lib.bank_history(args, client=client)
    assert ok is True
    client.cmd_bank_history.assert_called_once()


def test_bank_list_all_runs_cmd_when_authorized():
    from casino.commands.bank import lib

    args = _make_args(_session_moniker="root", _session_is_sysop=True)
    client = _make_client(moniker="root", is_sysop=True)
    with patch.object(lib, "_bank_access", return_value=True):
        ok = lib.bank_list_all(args, client=client)
    assert ok is True
    client.cmd_bank_list_all.assert_called_once()


def test_bank_balance_no_client_returns_false():
    """When the global casino client is unset, the handler fails
    fast without consulting the policy.
    """
    from casino.commands.bank import lib

    args = _make_args(_session_moniker="alice")
    with patch.object(lib, "get_client", return_value=None):
        ok = lib.bank_balance(args, client=None)
    assert ok is False


# ---------------------------------------------------------------------
# _require_authenticated_client gate (commands/_auth.py)


def test_bank_balance_rejects_unauthenticated_client():
    """A client in the registry that hasn't actually finished
    authenticating must not be able to drive any bank op."""
    from casino.commands.bank import lib

    client = _make_client(moniker="alice")
    client.authenticated = False

    args = _make_args(_session_moniker="alice")
    ok = lib.bank_balance(args, client=client)
    assert ok is False
    client.cmd_bank_balance.assert_not_called()


def test_bank_add_rejects_client_with_empty_moniker():
    from casino.commands.bank import lib

    client = _make_client(moniker="")

    args = _make_args(_session_moniker="alice")
    ok = lib.bank_add(args, client=client)
    assert ok is False
    client.cmd_bank_add.assert_not_called()


def test_bank_remove_rejects_unauthenticated_client():
    from casino.commands.bank import lib

    client = _make_client(moniker="alice")
    client.authenticated = False

    args = _make_args(_session_moniker="alice")
    ok = lib.bank_remove(args, client=client)
    assert ok is False
    client.cmd_bank_remove.assert_not_called()


def test_bank_transfer_rejects_unauthenticated_client():
    from casino.commands.bank import lib

    client = _make_client(moniker="alice")
    client.authenticated = False

    args = _make_args(_session_moniker="alice")
    ok = lib.bank_transfer(args, client=client)
    assert ok is False
    client.cmd_bank_transfer.assert_not_called()


def test_bank_approve_rejects_unauthenticated_client():
    from casino.commands.bank import lib

    client = _make_client(moniker="alice")
    client.authenticated = False

    args = _make_args(_session_moniker="alice")
    ok = lib.bank_approve(args, client=client)
    assert ok is False
    client.cmd_bank_approve.assert_not_called()


def test_bank_reject_rejects_unauthenticated_client():
    from casino.commands.bank import lib

    client = _make_client(moniker="alice")
    client.authenticated = False

    args = _make_args(_session_moniker="alice")
    ok = lib.bank_reject(args, client=client)
    assert ok is False
    client.cmd_bank_reject.assert_not_called()


def test_bank_pending_rejects_unauthenticated_client():
    from casino.commands.bank import lib

    client = _make_client(moniker="alice")
    client.authenticated = False

    args = _make_args(_session_moniker="alice")
    ok = lib.bank_pending(args, client=client)
    assert ok is False
    client.cmd_bank_pending.assert_not_called()


def test_bank_history_rejects_unauthenticated_client():
    from casino.commands.bank import lib

    client = _make_client(moniker="alice")
    client.authenticated = False

    args = _make_args(_session_moniker="alice")
    ok = lib.bank_history(args, client=client)
    assert ok is False
    client.cmd_bank_history.assert_not_called()


def test_bank_list_all_rejects_unauthenticated_client():
    from casino.commands.bank import lib

    client = _make_client(moniker="root", is_sysop=True)
    client.authenticated = False

    args = _make_args(_session_moniker="root", _session_is_sysop=True)
    ok = lib.bank_list_all(args, client=client)
    assert ok is False
    client.cmd_bank_list_all.assert_not_called()


def test_bank_menu_refuses_no_client():
    """The bank submenu must refuse to open without an
    authenticated client -- the gate fires before the heading
    / help / prompt so a user who hasn't connected cannot
    see [B] / [A] / [W] etc."""
    from casino.commands.bank import lib

    args = _make_args(_session_moniker="alice")
    with patch.object(lib, "get_client", return_value=None), \
         patch("bbsengine6.io.inputchoice") as mock_ic, \
         patch("bbsengine6.io.echo"):
        ok = lib.menu(args, client=None)
    assert ok is False
    mock_ic.assert_not_called()


def test_bank_menu_refuses_unauthenticated_client():
    from casino.commands.bank import lib

    client = _make_client(moniker="alice")
    client.authenticated = False

    args = _make_args(_session_moniker="alice")
    with patch.object(lib, "get_client", return_value=client), \
         patch("bbsengine6.io.inputchoice") as mock_ic, \
         patch("bbsengine6.io.echo"):
        ok = lib.menu(args, client=None)
    assert ok is False
    mock_ic.assert_not_called()


def test_bank_menu_opens_for_authenticated_client():
    from casino.commands.bank import lib

    client = _make_client(moniker="alice")
    args = _make_args(_session_moniker="alice")
    # inputchoice normally uppercases its return via ch.upper(); the
    # mock bypasses that path, so return uppercase directly so the
    # loop's ``if cmd == "Q": break`` fires on the first iteration.
    with patch.object(lib, "get_client", return_value=client), \
         patch("bbsengine6.io.inputchoice", return_value="Q") as mock_ic:
        ok = lib.menu(args, client=None)
    assert ok is True
    mock_ic.assert_called_once()
