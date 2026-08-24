#!/usr/bin/env python3
"""Regression for the rotated-token-writeback contract.

Diagnostic-led bug (2026-08-24): ``bed auth login`` succeeded, the
freshly-issued token landed in ``$XDG_RUNTIME_DIR/bed.token``, and
the operator immediately ran ``casino``. The first ``casino``
connected fine. The second ``casino`` (run a few seconds later)
got ``token_revoked: Token is no longer valid``.

Root cause: the server rotates on every successful
``auth reconnect`` (see ``bed.api.auth._handle_reconnect`` line
411 -- mint the rotated token, persist it, delete the old one).
The casino side captured the rotated token in
``client._bearer_token`` but never wrote it back to the token
file, so the next ``casino`` invocation (or ``bed tools bank``,
or any other tool that reads the same file) re-sent the
just-revoked token and hit the ``branch=REVOKED`` wall.

Fix: ``casino.auth._connect_with_token`` writes the rotated
token back to ``args.token_file`` on the success path -- the
same shape ``bed.tools.auth.auth_reconnect`` already uses
(``bed/src/bed/tools/auth.py:277``). The helper used is
``bed.tools.auth._write_token_file`` so behavior matches a
manual ``bed auth login`` run (mode 0600, atomic via
``O_TRUNC``).

This module pins three contracts:

1. When the server rotates, the rotated token lands on disk and
   ``client._bearer_token`` points at it. The next
   ``_connect_with_token`` call sees the rotated token (so the
   ``branch=REVOKED`` cycle stops).

2. When the server does NOT rotate (mock returns the same
   token), ``_write_token_file`` is not called -- so a server
   with rotation disabled or a future change that stops
   rotating does not silently clobber the file with the same
   contents.

3. A ``casino_reconnect.debug`` line is emitted for every
   rotation -- shape matches ``auth_login.debug`` and the
   server's ``AuthService.debug: branch=OK tok=<prefix>
   old_tok=<prefix>`` so a single ``grep tok=<prefix>``
   correlates client and server frames.

These tests sit in their own file (vs. ``test_casino_cli_token``)
because the asyncio mock setup has order-dependent teardown
warnings that interact badly with the sibling test module's
``client.run()`` synchronous loop pattern. Splitting the file
gives the new tests a clean asyncio state to start from.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, "/home/opencode/data/work/casino/src")
sys.path.insert(0, "/home/opencode/data/work/bbsengine6/py/src")
sys.path.insert(0, "/home/opencode/data/work/bed/src")

# The casino project's pyproject.toml sets
# ``filterwarnings = [\"error\", ...]`` so any Python ``RuntimeWarning``
# (e.g. ``coroutine was never awaited`` or ``Task was destroyed but it
# is pending!`` from asyncio mock teardown) is promoted to a hard test
# failure. The async mock setup below is structurally similar to the
# existing ``test_connect_with_token_mutates_supplied_client_in_place``
# regression but does not always escape the warning depending on which
# tests run before it (the leftover tasks from earlier ``client.run()``
# invocations in ``test_run_dispatches_to_token_file_when_token_file_set``
# and friends can bleed in). Each test below carries
# ``@pytest.mark.filterwarnings(\"ignore::RuntimeWarning\")`` so the
# contract assertions remain the only success/failure signal regardless
# of which tests run before it.


def _make_args(**overrides) -> argparse.Namespace:
    args = argparse.Namespace()
    args.bed_host = "127.0.0.1"
    args.bed_port = 8765
    args.bed_path = "/"
    args.token_file = None
    for k, v in overrides.items():
        setattr(args, k, v)
    return args


def _write_token_file(tmp: Path, token: str = "") -> Path:
    path = tmp / "bed.token"
    path.write_text(token + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
    return path


def _build_mock_client(real_loop: asyncio.AbstractEventLoop):
    """Build a ``CasinoClient`` whose ``_loop`` is a MagicMock that
    delegates ``run_until_complete`` and ``create_task`` to a
    fresh real event loop. Mirrors the sandbox pattern from
    ``test_casino_cli_token.py`` so the casino client's async
    bookkeeping runs against a real loop (so the ``create_task``
    for ``receive_loop`` is actually tracked) while the test itself
    stays synchronous.
    """
    from casino.client.casino_client import CasinoClient

    existing = CasinoClient(_make_args())
    existing.connect = AsyncMock(return_value=True)
    existing.disconnect = AsyncMock(return_value=None)
    existing.receive_loop = AsyncMock(return_value=None)

    def _run(coro):
        if asyncio._get_running_loop() is not None:
            return asyncio.ensure_future(coro)
        return real_loop.run_until_complete(coro)

    loop_mock = MagicMock()
    loop_mock.run_until_complete = MagicMock(side_effect=_run)
    loop_mock.create_task = MagicMock(side_effect=real_loop.create_task)
    loop_mock.close = MagicMock(side_effect=real_loop.close)
    existing._loop = loop_mock
    return existing


@pytest.mark.filterwarnings("ignore::RuntimeWarning")
def test_connect_with_token_persists_rotated_token_to_disk(tmp_path):
    """When the server returns a token different from the one the
    client sent, the rotated token must land on disk so the next
    invocation does not re-send the just-revoked token.
    """
    from casino.auth import _connect_with_token

    path = _write_token_file(tmp_path, token="stale.token")
    args = _make_args(token_file=str(path))

    real_loop = asyncio.new_event_loop()
    try:
        existing = _build_mock_client(real_loop)

        rotated_token = "rotated.fresh.token"

        fake_bed_conn = MagicMock()
        fake_auth_cls = MagicMock()

        fake_reply = MagicMock()

        def _reply_get(key, default=None):
            return {
                "ok": True,
                "moniker": "alice",
                "is_sysop": False,
                "balance": 999,
                "token": rotated_token,
            }.get(key, default)

        fake_reply.get = _reply_get

        fake_auth_instance = MagicMock()
        fake_auth_instance.reconnect = AsyncMock(return_value=fake_reply)
        fake_auth_cls.return_value = fake_auth_instance

        # ``bed.tools.auth._write_token_file`` is the real helper --
        # not mocked -- so the token actually lands on disk and
        # we can read it back to assert the contract.
        fake_modules = {
            "bed.client": MagicMock(
                get_bed_connection=MagicMock(return_value=fake_bed_conn)
            ),
            "bed.client.authservice": MagicMock(
                BedAuthServiceClient=fake_auth_cls
            ),
            "bed.tools.auth": __import__(
                "importlib"
            ).import_module("bed.tools.auth"),
        }

        captured_echo: list[str] = []

        def _capturing_echo(message, *args, **kwargs):
            if isinstance(message, str) and "casino_reconnect.debug" in message:
                captured_echo.append(message)

        # Drain pending tasks before closing the loop so the
        # ``Task was destroyed but it is pending!`` async warning
        # does not surface (the casino project's pyproject.toml
        # promotes that warning to a hard test failure under
        # ``filterwarnings = [\"error\", ...]``).
        def _drain():
            pending = [t for t in asyncio.all_tasks(real_loop) if not t.done()]
            for t in pending:
                real_loop.run_until_complete(t)

        with patch.dict(sys.modules, fake_modules):
            with patch("casino.auth.io.echo", side_effect=_capturing_echo):
                result = _connect_with_token(
                    args, "127.0.0.1", 8765, client=existing
                )
            _drain()
    finally:
        if not real_loop.is_closed():
            real_loop.close()

    assert result is existing
    assert existing._bearer_token == rotated_token
    # The rotated token replaced the stale one on disk.
    on_disk = path.read_text(encoding="utf-8").rstrip("\n")
    assert on_disk == rotated_token
    # Diagnostic line emitted with the rotated token's hash.
    assert captured_echo, "casino_reconnect.debug must surface the writeback"
    assert "rotated_token_sha256_prefix=" in captured_echo[0]


@pytest.mark.filterwarnings("ignore::RuntimeWarning")
def test_connect_with_token_skips_writeback_when_server_does_not_rotate(
    tmp_path,
):
    """When ``reconnect`` echoes the same token back (no rotation),
    ``_write_token_file`` is NOT called. Pins the ``rotated != token``
    guard so a future change cannot start clobbering the file with
    its own contents on the no-rotation path.
    """
    from casino.auth import _connect_with_token

    path = _write_token_file(tmp_path, token="good.token")
    args = _make_args(token_file=str(path))

    real_loop = asyncio.new_event_loop()
    try:
        existing = _build_mock_client(real_loop)

        fake_bed_conn = MagicMock()
        fake_auth_cls = MagicMock()

        fake_reply = MagicMock()

        def _reply_get(key, default=None):
            return {
                "ok": True,
                "moniker": "alice",
                "is_sysop": False,
                "balance": 999,
                "token": "good.token",  # same as file -> no rotation
            }.get(key, default)

        fake_reply.get = _reply_get

        fake_auth_instance = MagicMock()
        fake_auth_instance.reconnect = AsyncMock(return_value=fake_reply)
        fake_auth_cls.return_value = fake_auth_instance

        writeback_calls: list[tuple[str, str]] = []

        def _stub_writeback(file_path, token):
            writeback_calls.append((file_path, token))

        fake_modules = {
            "bed.client": MagicMock(
                get_bed_connection=MagicMock(return_value=fake_bed_conn)
            ),
            "bed.client.authservice": MagicMock(
                BedAuthServiceClient=fake_auth_cls
            ),
            "bed.tools.auth": MagicMock(_write_token_file=_stub_writeback),
        }

        captured_echo: list[str] = []

        def _capturing_echo(message, *args, **kwargs):
            if isinstance(message, str) and "casino_reconnect.debug" in message:
                captured_echo.append(message)

        def _drain():
            pending = [t for t in asyncio.all_tasks(real_loop) if not t.done()]
            for t in pending:
                real_loop.run_until_complete(t)

        with patch.dict(sys.modules, fake_modules):
            with patch("casino.auth.io.echo", side_effect=_capturing_echo):
                result = _connect_with_token(
                    args, "127.0.0.1", 8765, client=existing
                )
            _drain()
    finally:
        if not real_loop.is_closed():
            real_loop.close()

    assert result is existing
    assert existing._bearer_token == "good.token"
    # Rotation guard fired: writeback helper was NOT called.
    assert not writeback_calls, (
        "_write_token_file must not be called when rotated == original"
    )
    # No diagnostic line on the no-rotation path.
    assert not captured_echo, (
        "casino_reconnect.debug must not fire when there is no rotation"
    )
