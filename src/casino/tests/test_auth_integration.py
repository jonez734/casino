#!/usr/bin/env python3
"""End-to-end auth integration tests for casino's token-aware pipeline.

Mirrors the structure of ``bed/tests/test_auth_integration.py`` at the
casino layer:

- ``bbsengine6.casino.access()`` is the single source of truth for
  the per-op policy (verified by ``tests/test_casino_access.py``).
- ``casino.api._auth.check_access()`` runs the five-gate pipeline
  in order -- session resolve, wire-token validate, session-token
  validate, shape, then ``bbsengine6.casino.access()`` (verified by
  ``bed/tests/test_casino_service.py``).
- ``casino.auth._connect_with_token()`` is the CLI entry point that
  binds a saved bearer token to a freshly-opened WebSocket via
  :class:`bed.client.authservice.BedAuthServiceClient.reconnect`.

The tests in this file exercise the third layer without spinning
up a real bed daemon. ``BedAuthServiceClient.reconnect`` is mocked
so we can drive the success / failure paths deterministically and
assert that ``_connect_with_token`` propagates the reply correctly
into ``CasinoClient`` state (``authenticated``, ``moniker``,
``balance``, ``_bearer_token``).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import secrets
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


sys.path.insert(0, "/home/opencode/data/work/casino/src")
sys.path.insert(0, "/home/opencode/data/work/bbsengine6/py/src")
sys.path.insert(0, "/home/opencode/data/work/bed/src")


# ---------------------------------------------------------------------
# Helpers


def _make_args(**overrides) -> argparse.Namespace:
    args = argparse.Namespace()
    args.host = "127.0.0.1"
    args.port = 8765
    args.bed_host = "127.0.0.1"
    args.bed_port = 8765
    args.bed_path = "/"
    args.bed_call_timeout = 5.0
    args.token_file = None
    for k, v in overrides.items():
        setattr(args, k, v)
    return args


def _write_token_file(tmp: Path, token: str = "") -> Path:
    path = tmp / "bed.token"
    path.write_text(token + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
    return path


# ---------------------------------------------------------------------
# casino.auth._read_token_file


def test_read_token_file_returns_first_nonempty_line(tmp_path):
    from casino.auth import _read_token_file

    path = _write_token_file(tmp_path, token="abc.def")
    assert _read_token_file(str(path)) == "abc.def"


def test_read_token_file_skips_blank_and_comment_lines(tmp_path):
    from casino.auth import _read_token_file

    path = tmp_path / "bed.token"
    path.write_text(
        "\n# a comment line\n\nreal-token-xxx\n# trailing comment\n",
        encoding="utf-8",
    )
    assert _read_token_file(str(path)) == "real-token-xxx"


def test_read_token_file_returns_empty_for_missing(tmp_path):
    from casino.auth import _read_token_file

    assert _read_token_file(str(tmp_path / "nope")) == ""


def test_read_token_file_returns_empty_for_empty_file(tmp_path):
    from casino.auth import _read_token_file

    path = tmp_path / "empty.token"
    path.write_text("\n\n\n", encoding="utf-8")
    assert _read_token_file(str(path)) == ""


# ---------------------------------------------------------------------
# casino.auth._connect_with_token (mocked BedAuthServiceClient)


class _FakeReply:
    """Stub for the dict returned by ``BedAuthServiceClient.reconnect``."""

    def __init__(self, *, ok: bool, **fields):
        self._ok = ok
        self._fields = fields

    def get(self, key, default=None):
        if key == "ok":
            return self._ok
        return self._fields.get(key, default)


def _make_mock_casino_client(moniker: str = "alice") -> MagicMock:
    """Return a MagicMock that looks like :class:`CasinoClient` for
    ``_connect_with_token`` to drive.

    The mock's ``_loop`` is a real :class:`asyncio.AbstractEventLoop`
    (created on demand) so ``loop.create_task(coro)`` accepts the
    coroutine returned by the AsyncMock'd ``receive_loop``. ``run_until_complete``
    drives the AsyncMocks synchronously through the same loop. The
    loop is closed in :func:`_close_mock_client`.
    """
    client = MagicMock()
    client.connect = AsyncMock(return_value=True)
    client.disconnect = AsyncMock(return_value=None)
    client.receive_loop = AsyncMock(return_value=None)
    client.authenticated = False
    client.moniker = ""
    client.balance = 0
    client.is_sysop = False
    client._bearer_token = None

    real_loop = asyncio.new_event_loop()

    def _run(coro):
        # Drive the AsyncMock coroutine synchronously through the
        # same loop the mock uses so create_task() succeeds.
        if asyncio._get_running_loop() is not None:
            return asyncio.ensure_future(coro)
        return real_loop.run_until_complete(coro)

    loop_mock = MagicMock()
    loop_mock.run_until_complete = MagicMock(side_effect=_run)
    loop_mock.create_task = MagicMock(side_effect=real_loop.create_task)
    loop_mock.close = MagicMock(side_effect=real_loop.close)
    client._loop = loop_mock
    return client


def _run(coro):
    """Drive an awaitable synchronously for tests."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _consume(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _patch_bed_modules(fake_bed_conn, fake_auth_cls):
    """Replace ``bed.client`` / ``bed.client.authservice`` in
    ``sys.modules`` so the in-function imports in
    :func:`casino.auth._connect_with_token` resolve to the supplied
    fakes. The original modules are restored on context exit.
    """
    fake_bed_client = MagicMock(get_bed_connection=MagicMock(return_value=fake_bed_conn))
    fake_authservice = MagicMock(BedAuthServiceClient=fake_auth_cls)
    return patch.dict(sys.modules, {
        "bed.client": fake_bed_client,
        "bed.client.authservice": fake_authservice,
    })


def test_connect_with_token_succeeds_and_populates_client(tmp_path):
    from casino.auth import _connect_with_token

    path = _write_token_file(tmp_path, token="good.token")
    args = _make_args(token_file=str(path))

    fake_reply = _FakeReply(
        ok=True,
        moniker="alice",
        is_sysop=False,
        balance=1234,
        token="good.token",
    )

    client = _make_mock_casino_client()

    fake_bed_conn = MagicMock()
    fake_bed_conn._ws = None
    fake_auth_cls = MagicMock()
    fake_auth_cls.return_value.reconnect = AsyncMock(return_value=fake_reply)

    with _patch_bed_modules(fake_bed_conn, fake_auth_cls), \
         patch("casino.client.CasinoClient", return_value=client):
        result = _connect_with_token(args, "127.0.0.1", 8765)

    assert result is client
    assert client.authenticated is True
    assert client.moniker == "alice"
    assert client.balance == 1234
    assert client.is_sysop is False
    assert client._bearer_token == "good.token"
    # The casino client's own ws was opened (connect called).
    client.connect.assert_awaited_once()
    # Reconnect was called with the token read from the file.
    fake_auth_cls.return_value.reconnect.assert_awaited_once_with("good.token")
    # Receive loop was scheduled so server-pushed messages reach the
    # client (e.g. chat notifications).
    client._loop.create_task.assert_called_once()


def test_connect_with_token_rotates_token_to_reply(tmp_path):
    from casino.auth import _connect_with_token

    path = _write_token_file(tmp_path, token="old.token")
    args = _make_args(token_file=str(path))

    rotated = "new.token-from-server"
    fake_reply = _FakeReply(
        ok=True,
        moniker="alice",
        is_sysop=False,
        balance=0,
        token=rotated,
    )

    client = _make_mock_casino_client()

    fake_bed_conn = MagicMock()
    fake_bed_conn._ws = None
    fake_auth_cls = MagicMock()
    fake_auth_cls.return_value.reconnect = AsyncMock(return_value=fake_reply)

    with _patch_bed_modules(fake_bed_conn, fake_auth_cls), \
         patch("casino.client.CasinoClient", return_value=client):
        result = _connect_with_token(args, "127.0.0.1", 8765)

    assert result is client
    # The rotated token from the server takes precedence over the
    # file's token so subsequent ops see the freshest credentials.
    assert client._bearer_token == rotated


def test_connect_with_token_rejected_when_reconnect_fails(tmp_path):
    from casino.auth import _connect_with_token

    path = _write_token_file(tmp_path, token="stale.token")
    args = _make_args(token_file=str(path))

    fake_reply = _FakeReply(
        ok=False,
        code="token_revoked",
        message="Token is no longer valid",
    )

    client = _make_mock_casino_client()

    fake_bed_conn = MagicMock()
    fake_bed_conn._ws = None
    fake_auth_cls = MagicMock()
    fake_auth_cls.return_value.reconnect = AsyncMock(return_value=fake_reply)

    with _patch_bed_modules(fake_bed_conn, fake_auth_cls), \
         patch("casino.client.CasinoClient", return_value=client):
        result = _connect_with_token(args, "127.0.0.1", 8765)

    assert result is None
    assert client.authenticated is False
    assert client.moniker == ""
    client.disconnect.assert_awaited_once()


def test_connect_with_token_rejects_when_token_file_missing(tmp_path):
    from casino.auth import _connect_with_token

    args = _make_args(token_file=str(tmp_path / "absent.token"))

    fake_bed_conn = MagicMock()
    fake_bed_conn._ws = None
    fake_auth_cls = MagicMock()

    with _patch_bed_modules(fake_bed_conn, fake_auth_cls), \
         patch("casino.client.CasinoClient") as CC:
        result = _connect_with_token(args, "127.0.0.1", 8765)

    assert result is None
    # CasinoClient was never constructed because the file is empty.
    CC.assert_not_called()
    # Reconnect was never called either.
    fake_auth_cls.return_value.reconnect.assert_not_called()


def test_connect_with_token_rejects_when_token_file_empty(tmp_path):
    from casino.auth import _connect_with_token

    path = _write_token_file(tmp_path, token="")
    args = _make_args(token_file=str(path))

    fake_bed_conn = MagicMock()
    fake_bed_conn._ws = None
    fake_auth_cls = MagicMock()

    with _patch_bed_modules(fake_bed_conn, fake_auth_cls), \
         patch("casino.client.CasinoClient") as CC:
        result = _connect_with_token(args, "127.0.0.1", 8765)

    assert result is None
    CC.assert_not_called()
    fake_auth_cls.return_value.reconnect.assert_not_called()


# ---------------------------------------------------------------------
# Top-level ``connect`` dispatch


def test_connect_uses_token_path_when_token_file_set(tmp_path):
    """When ``args.token_file`` is set, ``connect`` dispatches to
    ``_connect_with_token`` instead of running ``auth_prompt``.
    """
    from casino import auth

    path = _write_token_file(tmp_path, token="good.token")
    args = _make_args(token_file=str(path))

    fake_reply = _FakeReply(
        ok=True,
        moniker="alice",
        is_sysop=False,
        balance=42,
        token="good.token",
    )
    expected_client = MagicMock()
    expected_client.moniker = "alice"
    expected_client.balance = 42
    expected_client._loop = MagicMock()

    with patch.object(auth, "_connect_with_token", return_value=expected_client):
        result = auth.connect(args)

    assert result is expected_client


def test_connect_falls_back_to_legacy_prompt_when_token_file_unset():
    """When ``args.token_file`` is not set, ``connect`` falls back
    to the legacy prompt-based ``auth_prompt`` flow.
    """
    from casino import auth

    args = _make_args()  # token_file=None by default

    expected_client = _make_mock_casino_client()
    expected_client.moniker = "alice"
    expected_client.balance = 100
    expected_client.authenticated = True  # set by auth_prompt-style flow

    with patch.object(auth, "_connect_with_token") as token_path, \
         patch("casino.client.CasinoClient", return_value=expected_client):
        async def _ok_prompt(args, client):
            return True
        with patch.object(auth, "auth_prompt", _ok_prompt):
            result = auth.connect(args)

    assert result is expected_client
    token_path.assert_not_called()
    # Legacy auth_prompt was driven (its return value was consumed by
    # the connect flow).
    expected_client.connect.assert_awaited_once()
    expected_client.disconnect.assert_not_called()


# ---------------------------------------------------------------------
# bbsengine6.casino.access() end-to-end with token-derived claims


def test_casino_access_uses_token_claims_for_kick_player_authorization():
    """A ``bbsengine6.casino.access("kick_player")`` decision driven
    from a verified token's claims (with a synthetic session whose
    attributes match the claims) gates correctly: a sysop claim
    passes; a non-owner non-sysop claim denies; the in-message
    owner check matches the claim-derived moniker.
    """
    from bbsengine6.casino import access

    args = argparse.Namespace()

    # Sysop claim wins regardless of owner. The handler always passes
    # a session object; access() prefers claim-derived is_sysop over
    # the in-memory attribute when ``message["claims"]`` is set.
    base_msg = {
        "claims": {
            "version": 1,
            "moniker": "root",
            "is_sysop": True,
            "session_id": "s-root",
            "bed_instance_id": "test",
            "websocket_id": "ws-root",
            "expires_at": 1_000_000.0,
            "issued_at": 1_000.0,
        },
        "table_moniker": "t1",
        "owner": "alice",
    }
    state = SimpleNamespace(moniker="root", is_sysop=True, table_moniker=None)
    assert access(args, "kick_player", session=state, message=base_msg) is True

    # Non-sysop claim + matching owner wins.
    state.moniker = "alice"
    state.is_sysop = False
    base_msg["claims"]["moniker"] = "alice"
    base_msg["claims"]["is_sysop"] = False
    assert access(args, "kick_player", session=state, message=base_msg) is True

    # Non-sysop claim + non-matching owner denies.
    state.moniker = "carol"
    base_msg["claims"]["moniker"] = "carol"
    assert access(args, "kick_player", session=state, message=base_msg) is False


def test_casino_access_seat_at_check_uses_session_attribute():
    """For table-bound gameplay ops (``bet``, ``hit``, etc.) the
    policy consults the session's ``table_moniker`` attribute. A
    session bound to a different table is denied.
    """
    from bbsengine6.casino import access

    args = argparse.Namespace()
    state = SimpleNamespace(
        moniker="alice",
        is_sysop=False,
        table_moniker="t-other",
    )
    msg = {"table_moniker": "t1"}
    assert access(args, "bet", session=state, message=msg) is False

    state.table_moniker = "t1"
    assert access(args, "bet", session=state, message=msg) is True
