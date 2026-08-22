#!/usr/bin/env python3
"""Regression tests for the merged ``casino`` CLI's ``--token-file`` wiring.

Three regression pins:

1. ``casino.lib.buildargs()`` registers ``--token-file`` on the merged
   parser. Without this, ``casino --token-file /path/to/token`` is
   rejected by argparse as an unknown flag (the symptom reported when
   the bearer-token PR was "acting as though not built").

2. ``CasinoClient.run()`` dispatches to
   :func:`casino.auth._connect_with_token` when ``args.token_file`` is
   set (either by an explicit ``--token-file`` flag or by the
   ``bed.tools._token.ensure_token_file_arg`` default-path
   resolution in :func:`casino.__main__.main`). The legacy prompt
   path (``self.cmd_auth``) is bypassed.

3. ``casino.auth._resolve_token_file`` silently clears
   ``args.token_file`` when the resolved path points at an empty or
   missing file, so the downstream prompt path runs cleanly without
   the operator first running ``bed auth login``.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, "/home/opencode/data/work/casino/src")
sys.path.insert(0, "/home/opencode/data/work/bbsengine6/py/src")
sys.path.insert(0, "/home/opencode/data/work/bed/src")


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


# ---------------------------------------------------------------------
# casino.lib.buildargs registers --token-file


def test_lib_buildargs_registers_token_file_flag():
    """``casino.lib.buildargs()`` registers ``--token-file`` on the
    merged CLI's argparse so ``casino --token-file <path>`` is a
    known flag rather than an argparse error.

    Regression pin: the bearer-token PR's modules were landed but
    ``--token-file`` was never added to the merged parser, so the
    CLI rejected the flag with
    ``argparse: unrecognized arguments: --token-file /path``.
    """
    import casino.lib as lib

    parser = lib.buildargs()
    action_strings = []
    for action in parser._actions:
        action_strings.extend(action.option_strings)
    assert "--token-file" in action_strings, (
        f"--token-file not registered; got: {action_strings}"
    )


# ---------------------------------------------------------------------
# casino.auth.buildargs parser kwarg


def test_buildargs_accepts_parser_kwarg_directly():
    """``casino.auth.buildargs(args, parser=parser)`` registers the
    flag on the supplied parser. Pins the new signature (parser is
    a kwarg, not a hidden ``args._parser`` attribute)."""
    import argparse as _argparse

    from casino import auth

    parser = _argparse.ArgumentParser()
    auth.buildargs(args=None, parser=parser)
    action_strings = []
    for action in parser._actions:
        action_strings.extend(action.option_strings)
    assert "--token-file" in action_strings


def test_buildargs_without_parser_sets_args_token_file_default():
    """``casino.auth.buildargs(args)`` (no parser, BBS-dispatch path)
    still ensures ``args.token_file`` defaults to None. Backwards-
    compatible with the BBS-dispatch call shape
    (``bbsengine6.module.runmodule`` → ``casino.auth.buildargs``)."""
    from casino import auth

    args = argparse.Namespace()
    auth.buildargs(args)
    assert args.token_file is None


# ---------------------------------------------------------------------
# CasinoClient.run dispatch


def test_run_dispatches_to_token_file_when_token_file_set(tmp_path):
    """When ``args.token_file`` points at a non-empty token file,
    ``CasinoClient.run()`` calls
    :func:`casino.auth._connect_with_token` with ``client=self`` so
    the post-auth menu loop can run on the same instance.

    Pins the fix for the merged CLI's BED-mode entry point: prior
    to this change, ``run()`` went straight to ``self.cmd_auth()``
    (the legacy prompt flow) regardless of ``args.token_file``.
    """
    from casino.client.casino_client import CasinoClient

    path = _write_token_file(tmp_path, token="good.token")
    args = _make_args(token_file=str(path))

    client = CasinoClient(args)
    client.cmd_auth = AsyncMock(return_value=True)
    client.connect = AsyncMock(return_value=True)
    client.receive_loop = AsyncMock(return_value=None)

    # The helper mutates the supplied client in place; let it run
    # against the real (mocked) bed modules via the patch context.
    fake_reply = {
        "ok": True,
        "moniker": "alice",
        "is_sysop": False,
        "balance": 100,
        "token": "good.token",
    }

    fake_bed_conn = MagicMock()
    fake_auth_instance = MagicMock()
    fake_auth_instance.reconnect = AsyncMock(return_value=fake_reply)
    fake_auth_cls = MagicMock(return_value=fake_auth_instance)

    fake_modules = {
        "bed.client": MagicMock(get_bed_connection=MagicMock(return_value=fake_bed_conn)),
        "bed.client.authservice": MagicMock(BedAuthServiceClient=fake_auth_cls),
    }

    with patch.dict(sys.modules, fake_modules), \
         patch(
             "casino.client.casino_client._client_menu", return_value="Q"
         ):
        # Mock _client_menu to "Q" so the post-auth loop exits on
        # the first iteration after authentication.
        client.run()

    # cmd_auth was NOT called -- token path was used.
    client.cmd_auth.assert_not_called()
    # client.connect() was also NOT called -- the token path opens
    # the WS via CasinoClient.connect inside _connect_with_token,
    # but on the same instance.
    # (cmd_auth.assert_not_called is the primary pin.)
    # State propagated onto the in-place client.
    assert client.authenticated is True
    assert client.moniker == "alice"
    assert client.balance == 100
    assert client._bearer_token == "good.token"


def test_run_falls_back_to_prompt_when_token_file_unset():
    """When ``args.token_file`` is None (operator ran ``casino`` with
    no ``--token-file`` and no default token file), ``run()`` falls
    through to the legacy prompt path. The token-file helper is NOT
    called."""
    from casino.client.casino_client import CasinoClient

    args = _make_args(token_file=None)

    client = CasinoClient(args)
    client.cmd_auth = AsyncMock(return_value=True)
    client.connect = AsyncMock(return_value=True)
    client.receive_loop = AsyncMock(return_value=None)

    with patch("casino.auth._connect_with_token") as mock_connect, \
         patch("casino.client.casino_client._client_menu", return_value="Q"):
        client.run()

    mock_connect.assert_not_called()
    client.cmd_auth.assert_awaited_once()
    client.connect.assert_awaited_once()


# ---------------------------------------------------------------------
# casino.auth._resolve_token_file silent fallback


def test_resolve_token_file_clears_when_default_file_empty(tmp_path, monkeypatch):
    """When ``args.token_file`` is unset, ``_resolve_token_file`` fills
    in the default ``$XDG_RUNTIME_DIR/bed.token`` path. If that file
    is empty (or missing), ``_resolve_token_file`` clears
    ``args.token_file`` back to ``None`` so the prompt path runs.

    Pins the silent-fallback behavior so an operator running
    ``casino`` before ``bed auth login`` still gets the prompt.
    """
    from casino.auth import _resolve_token_file

    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    args = _make_args(token_file=None)
    _resolve_token_file(args)
    # File does not exist yet -> _read_token_file returns "" ->
    # _resolve_token_file clears args.token_file.
    assert args.token_file is None
    # Sanity: the default path was indeed the path the helper
    # started with (verified by re-running _token.ensure_token_file_arg
    # on a fresh args).
    from bed.tools import _token
    fresh = _make_args(token_file=None)
    _token.ensure_token_file_arg(fresh)
    assert fresh.token_file == str(tmp_path / "bed.token")


def test_resolve_token_file_keeps_nonempty_default(tmp_path, monkeypatch):
    """When the default ``$XDG_RUNTIME_DIR/bed.token`` exists and has
    content, ``_resolve_token_file`` leaves ``args.token_file``
    pointing at it so :meth:`CasinoClient.run` takes the token-file
    path."""
    from casino.auth import _resolve_token_file

    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    _write_token_file(tmp_path, token="abc.def")
    args = _make_args(token_file=None)
    _resolve_token_file(args)
    assert args.token_file == str(tmp_path / "bed.token")


def test_resolve_token_file_respects_explicit_path(tmp_path):
    """When the operator passes ``--token-file`` explicitly
    (``args.token_file`` already set), ``_resolve_token_file`` does
    NOT overwrite it with the default path."""
    from casino.auth import _resolve_token_file

    explicit = _write_token_file(tmp_path, token="explicit.token")
    args = _make_args(token_file=str(explicit))
    _resolve_token_file(args)
    assert args.token_file == str(explicit)


# ---------------------------------------------------------------------
# _connect_with_token in-place mutation contract


def test_connect_with_token_mutates_supplied_client_in_place(tmp_path):
    """``_connect_with_token(args, host, port, client=existing)``
    mutates ``existing`` in place: opens the loop, opens the WS,
    calls ``BedAuthServiceClient.reconnect``, and populates
    ``authenticated/moniker/balance/_bearer_token`` on
    ``existing``.

    Pins the in-place mutation contract so :meth:`CasinoClient.run`
    can use a pre-built ``self`` without constructing a second
    client. Default ``client=None`` behavior is preserved for the
    BBS-dispatch path (:func:`casino.auth.connect`).
    """
    import asyncio

    from casino.auth import _connect_with_token
    from casino.client.casino_client import CasinoClient

    path = _write_token_file(tmp_path, token="good.token")
    args = _make_args(token_file=str(path))

    existing = CasinoClient(args)
    existing.connect = AsyncMock(return_value=True)
    existing.disconnect = AsyncMock(return_value=None)
    existing.receive_loop = AsyncMock(return_value=None)

    real_loop = asyncio.new_event_loop()

    def _run(coro):
        if asyncio._get_running_loop() is not None:
            return asyncio.ensure_future(coro)
        return real_loop.run_until_complete(coro)

    loop_mock = MagicMock()
    loop_mock.run_until_complete = MagicMock(side_effect=_run)
    loop_mock.create_task = MagicMock(side_effect=real_loop.create_task)
    loop_mock.close = MagicMock(side_effect=real_loop.close)
    existing._loop = loop_mock

    fake_bed_conn = MagicMock()
    fake_auth_cls = MagicMock()
    fake_reply = MagicMock()

    def _reply_get(key, default=None):
        return {
            "ok": True,
            "moniker": "alice",
            "is_sysop": False,
            "balance": 999,
            "token": "good.token",
        }.get(key, default)

    fake_reply.get = _reply_get

    fake_auth_instance = MagicMock()
    fake_auth_instance.reconnect = AsyncMock(return_value=fake_reply)
    fake_auth_cls.return_value = fake_auth_instance

    fake_modules = {
        "bed.client": MagicMock(get_bed_connection=MagicMock(return_value=fake_bed_conn)),
        "bed.client.authservice": MagicMock(BedAuthServiceClient=fake_auth_cls),
    }

    try:
        with patch.dict(sys.modules, fake_modules):
            result = _connect_with_token(args, "127.0.0.1", 8765, client=existing)
    finally:
        if not real_loop.is_closed():
            real_loop.close()

    assert result is existing, "_connect_with_token must return the supplied client"
    assert existing.authenticated is True
    assert existing.moniker == "alice"
    assert existing.balance == 999
    assert existing._bearer_token == "good.token"
