#!/usr/bin/env python3
"""Pin casino's auth-prompt UX against ``bed auth login``.

The casino auth-prompt path (``casino.auth.auth_prompt``) and the
``bed auth login`` path (``bed.tools.auth.auth_login``) used to share
no code: casino asked for ``Moniker:`` and ``Password:``, bed asked
for ``moniker:`` and ``password:`` -- and the markup differed too
(casino wrapped only the moniker prompt, bed wrapped both). Operators
running ``bed auth login`` and then ``casino`` saw two different
prompt UIs for what is conceptually the same action.

This file pins the unified UX:

1. ``casino.auth.auth_prompt`` calls
   :func:`bed.tools.auth._collect_credentials` so the prompt strings
   are byte-identical to ``bed auth login``.
2. ``casino.auth.auth_prompt`` persists the freshly-minted token
   via :func:`bed.tools.auth._persist_token` so the next ``casino``
   invocation picks up the token file at the default path (the
   same file ``bed auth login`` writes) and skips prompting.
3. The casino WS only ever sees a ``reconnect`` envelope from the
   prompt path -- never a fresh ``auth`` envelope -- because the
   server binds the new token to the open socket via the same wire
   shape :func:`casino.auth._connect_with_token` uses.
4. ``handle_message`` recognises ``reconnect_result`` (the
   server-side reply to ``reconnect``) and updates the same client
   state (``authenticated``, ``moniker``, ``balance``,
   ``_bearer_token``) that the legacy ``auth_result`` path used to
   populate.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, "/home/opencode/data/work/casino/src")
sys.path.insert(0, "/home/opencode/data/work/bed/src")


def _make_args() -> argparse.Namespace:
    args = argparse.Namespace()
    args.bed_host = "127.0.0.1"
    args.bed_port = 8765
    args.bed_path = "/"
    args.token_file = None
    args.moniker = None
    args.password = None
    args.debug = False
    return args


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_auth_prompt_reuses_bed_collect_credentials():
    """``casino.auth.auth_prompt`` delegates the ``moniker:`` /
    ``password:`` prompts to ``bed.tools.auth._collect_credentials``
    so the strings are byte-identical to ``bed auth login``. The
    prompt must NOT re-implement the prompts via
    ``bbsengine6.io.inputstring`` directly -- that is the regression
    we are guarding against.
    """
    from casino import auth

    seen_by_bed = []

    def fake_collect(args):
        # Mimic what the real ``_collect_credentials`` does first:
        # resolve the default token-file path so the token bed
        # persists lands at the same default location
        # ``bed auth login`` would use.
        from bed.tools import _token as _bed_token
        _bed_token.ensure_token_file_arg(args)
        seen_by_bed.append(args)
        return ("alice", "s3cret")

    class FakeConn:
        def __init__(self, args):
            pass

        def force_close(self):
            pass

    class FakeAuthSvc:
        def __init__(self, conn):
            pass

        async def login(self, moniker, password):
            return {
                "ok": True,
                "moniker": moniker,
                "is_sysop": False,
                "session_id": "sess-1",
                "token": "tok-from-bed",
                "expires_at": "2099-01-01T00:00:00Z",
                "balance": 100,
            }

    fake_client = MagicMock()
    fake_client.send = AsyncMock()
    fake_client.moniker = ""
    fake_client.balance = 0
    fake_client.authenticated = False
    fake_client._bearer_token = None

    with patch("bed.tools.auth._collect_credentials", side_effect=fake_collect), \
         patch("bed.tools.auth._persist_token") as persist, \
         patch("bed.client.authservice.BedAuthServiceClient", FakeAuthSvc), \
         patch("bed.client.connection.BedConnection", FakeConn):
        result = _run(auth.auth_prompt(_make_args(), fake_client))

    assert result is True
    assert len(seen_by_bed) == 1, "casino must call _collect_credentials exactly once"
    # The Namespace handed to bed carries the bed-shaped fields
    # (subcommand, bed_host, bed_port, token_file) so the helper
    # resolves the default token path the same way ``bed auth login``
    # does.
    bed_args = seen_by_bed[0]
    assert bed_args.subcommand == "login"
    assert bed_args.bed_host == "127.0.0.1"
    assert bed_args.bed_port == 8765
    assert bed_args.bed_path == "/"
    # The token file path was resolved to the default (the same path
    # ``bed auth login`` would have used).
    assert bed_args.token_file, (
        "casino must populate token_file via _ensure_token_file_arg "
        "inside _collect_credentials so the persisted token lands at "
        "the same default path bed uses"
    )
    # _persist_token was called with the reply that bed returned.
    persist.assert_called_once()
    reply_arg = persist.call_args.args[0]
    assert reply_arg.get("token") == "tok-from-bed"


def test_auth_prompt_does_not_re_prompt_directly():
    """Belt-and-braces guard: the prompt path must not call
    ``io.inputstring`` / ``util.inputpassword`` from
    ``bbsengine6`` directly. The whole point of delegating to
    ``_collect_credentials`` is that the prompt UX lives in one
    place. If a future refactor re-introduces a direct prompt call,
    this test catches it before the prompt strings drift apart
    again.
    """
    from casino import auth
    import bbsengine6.io as _bbsio
    import bbsengine6.util as _bbsutil

    class FakeConn:
        def __init__(self, args):
            pass

        def force_close(self):
            pass

    class FakeAuthSvc:
        def __init__(self, conn):
            pass

        async def login(self, moniker, password):
            return {
                "ok": True,
                "moniker": moniker,
                "is_sysop": False,
                "session_id": "sess-1",
                "token": "tok",
                "expires_at": "2099-01-01T00:00:00Z",
                "balance": 0,
            }

    fake_client = MagicMock()
    fake_client.send = AsyncMock()
    fake_client.moniker = ""
    fake_client.balance = 0
    fake_client.authenticated = False
    fake_client._bearer_token = None

    direct_inputstring = MagicMock(return_value="alice")
    direct_inputpassword = MagicMock(return_value="pw")

    with patch.object(auth, "io", wraps=_bbsio) as wrapped_io, \
         patch.object(auth, "util", wraps=_bbsutil) as wrapped_util, \
         patch("bed.tools.auth._collect_credentials", return_value=("alice", "pw")), \
         patch("bed.tools.auth._persist_token"), \
         patch("bed.client.authservice.BedAuthServiceClient", FakeAuthSvc), \
         patch("bed.client.connection.BedConnection", FakeConn):
        # Track direct calls to the prompt helpers via the casino.auth
        # module's own bindings (not bed's _collect_credentials, which
        # is mocked).
        with patch.object(wrapped_io, "inputstring", direct_inputstring), \
             patch.object(wrapped_util, "inputpassword", direct_inputpassword):
            result = _run(auth.auth_prompt(_make_args(), fake_client))

    assert result is True
    # bed.tools.auth._collect_credentials is patched, so any direct
    # casino.auth.io.inputstring / casino.auth.util.inputpassword call
    # here would have come from casino's own prompt code -- not from
    # the bed helper. None should fire.
    direct_inputstring.assert_not_called()
    direct_inputpassword.assert_not_called()


def test_auth_prompt_writes_token_via_bed_persist():
    """``casino.auth.auth_prompt`` must persist the freshly-minted
    token via :func:`bed.tools.auth._persist_token` so the next
    ``casino`` invocation can skip prompting by reading the same
    token file ``bed auth login`` writes.
    """
    from casino import auth

    persist_calls = []

    def fake_collect(args):
        from bed.tools import _token as _bed_token
        _bed_token.ensure_token_file_arg(args)
        return ("alice", "pw")

    def fake_persist(reply, bed_args):
        persist_calls.append((reply, bed_args))
        return True

    class FakeConn:
        def __init__(self, args):
            pass

        def force_close(self):
            pass

    class FakeAuthSvc:
        def __init__(self, conn):
            pass

        async def login(self, moniker, password):
            return {
                "ok": True,
                "moniker": moniker,
                "is_sysop": False,
                "session_id": "sess-1",
                "token": "tok-persisted",
                "expires_at": "2099-01-01T00:00:00Z",
                "balance": 0,
            }

    fake_client = MagicMock()
    fake_client.send = AsyncMock()
    fake_client.moniker = ""
    fake_client.balance = 0
    fake_client.authenticated = False
    fake_client._bearer_token = None

    with patch("bed.tools.auth._collect_credentials", side_effect=fake_collect), \
         patch("bed.tools.auth._persist_token", side_effect=fake_persist), \
         patch("bed.client.authservice.BedAuthServiceClient", FakeAuthSvc), \
         patch("bed.client.connection.BedConnection", FakeConn):
        result = _run(auth.auth_prompt(_make_args(), fake_client))

    assert result is True
    assert len(persist_calls) == 1
    reply, bed_args = persist_calls[0]
    # The reply handed to _persist_token carries the same token
    # the server returned to the one-shot login -- not a fabricated
    # value, not a fallback. (A future regression that computed the
    # token locally and passed it to _persist_token would silently
    # desync the file from the server's view.)
    assert reply.get("token") == "tok-persisted"
    assert bed_args.token_file, "_persist_token needs the resolved token_file path"


def test_handle_message_treats_reconnect_result_as_auth_result():
    """The server replies to ``reconnect`` with ``reconnect_result``
    (not ``auth_result``). Casino's ``handle_message`` must update
    the same client state from either envelope -- the prompt-driven
    flow now sends ``reconnect`` to bind the freshly-minted token to
    its already-open WS, so the rotating-token capture path lives
    here, not just on the legacy ``auth_result`` branch.
    """
    from unittest.mock import patch

    from casino.client import CasinoClient

    client = CasinoClient(argparse.Namespace(bed_host="127.0.0.1", bed_port=8765, bed_path="/"))

    with patch("casino.client.casino_client.io.echo"):
        _run(
            client.handle_message(
                {
                    "type": "reconnect_result",
                    "success": True,
                    "moniker": "alice",
                    "balance": 99,
                    "token": "rotated.tok",
                    "expires_at": "2099-01-01T00:00:00Z",
                }
            )
        )

    assert client.authenticated is True
    assert client.moniker == "alice"
    assert client.balance == 99
    # The rotated token is captured unconditionally so the next op
    # uses the new one (the old token is no longer valid against the
    # server's token store).
    assert client._bearer_token == "rotated.tok"


def test_handle_message_reconnect_result_rotation_overwrites_token():
    """``reconnect`` rotates the token. A subsequent ``reconnect_result``
    must replace the in-memory ``_bearer_token`` (the old one is
    gone from the server), not merely capture if absent. Pin that the
    rotation path on the legacy prompt flow is the same shape as the
    token-file path: the server's reply is the source of truth.
    """
    from unittest.mock import patch

    from casino.client import CasinoClient

    client = CasinoClient(argparse.Namespace(bed_host="127.0.0.1", bed_port=8765, bed_path="/"))
    client._bearer_token = "old.token"

    with patch("casino.client.casino_client.io.echo"):
        _run(
            client.handle_message(
                {
                    "type": "reconnect_result",
                    "success": True,
                    "moniker": "alice",
                    "balance": 0,
                    "token": "fresh.token",
                    "expires_at": "2099-01-01T00:00:00Z",
                }
            )
        )

    assert client._bearer_token == "fresh.token", (
        "reconnect_result must overwrite _bearer_token with the "
        "rotated value; otherwise the next op is rejected as "
        "token_revoked"
    )


def test_handle_message_reconnect_result_failure_does_not_clear_token():
    """A failed ``reconnect_result`` (``success: false``) leaves
    ``_bearer_token`` untouched. The legacy prompt flow would still
    have a valid token from a previous successful login; a transient
    reconnect failure must not blow it away. Mirrors the
    ``auth_result`` failure branch.
    """
    from unittest.mock import patch

    from casino.client import CasinoClient

    client = CasinoClient(argparse.Namespace(bed_host="127.0.0.1", bed_port=8765, bed_path="/"))
    client._bearer_token = "still.valid"

    with patch("casino.client.casino_client.io.echo"):
        _run(
            client.handle_message(
                {
                    "type": "reconnect_result",
                    "success": False,
                    "moniker": "alice",
                    "message": "transient blip",
                    "token": "evil.injected",
                }
            )
        )

    assert client._bearer_token == "still.valid", (
        "a failed reconnect_result must not capture the server-supplied "
        "token field"
    )
    assert client.authenticated is False


def test_auth_prompt_token_envelope_is_reconnect_not_auth():
    """Pin the wire shape: casino's prompt path sends ``reconnect``
    (not ``auth``) on the casino WS. The server's ``_handle_auth``
    accepts only moniker+password credentials and would reject a
    token envelope there; the server's ``_handle_reconnect`` is the
    one that binds a freshly-minted token to an open WS. Sending
    the wrong envelope is a silent regression: the prompt would
    "succeed" from casino's point of view, but the server would
    bounce the call and the next op would fail at the wire-token
    gate.
    """
    from casino import auth

    class FakeConn:
        def __init__(self, args):
            pass

        def force_close(self):
            pass

    class FakeAuthSvc:
        def __init__(self, conn):
            pass

        async def login(self, moniker, password):
            return {
                "ok": True,
                "moniker": moniker,
                "is_sysop": False,
                "session_id": "sess-1",
                "token": "tok",
                "expires_at": "2099-01-01T00:00:00Z",
                "balance": 0,
            }

    fake_client = MagicMock()
    fake_client.send = AsyncMock()
    fake_client.moniker = ""
    fake_client.balance = 0
    fake_client.authenticated = False
    fake_client._bearer_token = None

    with patch("bed.tools.auth._collect_credentials", return_value=("alice", "pw")), \
         patch("bed.tools.auth._persist_token"), \
         patch("bed.client.authservice.BedAuthServiceClient", FakeAuthSvc), \
         patch("bed.client.connection.BedConnection", FakeConn):
        _run(auth.auth_prompt(_make_args(), fake_client))

    fake_client.send.assert_awaited_once()
    sent = fake_client.send.await_args.args[0]
    assert sent["type"] == "reconnect", (
        f"casino prompt must send 'reconnect', got {sent['type']!r}; "
        "sending 'auth' with a token field would be silently "
        "rejected by the server's _handle_auth"
    )
    assert sent.get("token") == "tok"
    # And explicitly: no credentials on the casino WS, ever.
    assert "moniker" not in sent
    assert "password" not in sent
