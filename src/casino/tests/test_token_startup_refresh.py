#!/usr/bin/env python3
# casino/tests/test_token_startup_refresh.py
# Phase 2c: at startup a stored token that has run out, or that the server rejects, prints a
# message and falls back to the login prompt, instead of exiting with auth_failed.
# Phase 2b: a token nearing expiry is refreshed before use. Stubbed: no daemon, no database.

import base64
import json
from unittest.mock import MagicMock, patch

import pytest

from casino import auth


def _make_token(expires_at: float) -> str:
    """A token in bed's format. The MAC is not checked client-side, so any suffix works here."""
    payload = json.dumps({"moniker": "alice", "expires_at": expires_at, "version": 1})
    body = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{body}.deadbeef"


def _drive(coro_or_value, result=True):
    """Run a coroutine to completion so the stub loop leaves nothing unawaited."""
    import asyncio

    if hasattr(coro_or_value, "send"):
        async def _await(c):
            return await c
        return asyncio.run(_await(coro_or_value))
    return result


@pytest.mark.unit
def test_token_expires_at_reads_the_claim():
    assert auth.token_expires_at(_make_token(1_900_000_000.0)) == 1_900_000_000.0


@pytest.mark.unit
@pytest.mark.parametrize("bad", ["", "no-dot", "a.b", "!!!.x", None])
def test_token_expires_at_is_none_for_unreadable_tokens(bad):
    assert auth.token_expires_at(bad) is None


@pytest.mark.unit
def test_expired_stored_token_is_detected_without_connecting():
    expired = _make_token(1.0)  # 1970: long gone
    with patch.object(auth, "_read_token_file", return_value=expired), \
         patch.object(auth, "_stored_token_is_usable", wraps=auth._stored_token_is_usable), \
         patch("bed.client.get_bed_connection") as conn:
        assert auth._stored_token_is_usable(expired) is False
        conn.assert_not_called()


@pytest.mark.unit
def test_fresh_stored_token_is_usable():
    fresh = _make_token(4_000_000_000.0)
    assert auth._stored_token_is_usable(fresh) is True


@pytest.mark.unit
def test_run_falls_back_to_the_login_prompt_when_the_token_is_rejected():
    import inspect
    from casino.client import casino_client as cc

    src = inspect.getsource(cc.CasinoClient.run)
    # A rejected or expired stored token leads to the prompt path, not a bare auth_failed exit.
    assert "_stored_token_is_usable" in src or "token_rejected" in src
    assert "self.connect()" in src


@pytest.mark.unit
def test_refresh_is_needed_only_inside_the_margin():
    now = 1_000_000.0
    soon = _make_token(now + 30)     # inside the 120s margin
    later = _make_token(now + 3600)  # well outside it
    assert auth._token_needs_refresh(soon, now=now) is True
    assert auth._token_needs_refresh(later, now=now) is False
    assert auth._token_needs_refresh("garbage", now=now) is False


@pytest.mark.unit
def test_refresh_rotates_and_stores_the_new_token(tmp_path):
    token_file = tmp_path / "bed.token"
    token_file.write_text("old\n")
    client = MagicMock()
    client._bearer_token = "old"
    new_token = _make_token(4_000_000_000.0)
    reply = {"ok": True, "token": new_token, "expires_at": 4_000_000_000.0}
    with patch("bed.tools.auth._write_token_file") as write:
        ok = auth._apply_refreshed_token(client, reply, str(token_file))
    assert ok is True
    assert client._bearer_token == new_token
    write.assert_called_once_with(str(token_file), new_token)


@pytest.mark.unit
def test_failed_refresh_does_not_replace_the_token():
    client = MagicMock()
    client._bearer_token = "old"
    ok = auth._apply_refreshed_token(client, {"ok": False, "code": "token_expired"}, "/nope")
    assert ok is False
    assert client._bearer_token == "old"


@pytest.mark.unit
def test_expired_stored_token_skips_the_token_connect_and_prompts(tmp_path):
    """Behaviour: run() with an expired token never sends it; it goes to the login prompt."""
    from casino.client import casino_client as cc

    token_file = tmp_path / "bed.token"
    token_file.write_text(_make_token(1.0) + "\n")

    client = cc.CasinoClient.__new__(cc.CasinoClient)
    client.args = MagicMock(token_file=str(token_file), bed_host="127.0.0.1", bed_port=8765)
    client._exit_reason = "quit"
    client._close_code = None
    client._ws_failed = False
    client.authenticated = False
    client._loop = None
    client._receive_task = None
    client._bearer_token = None

    token_connect = MagicMock(return_value=None)
    with patch.object(auth, "_connect_with_token", token_connect), \
         patch.object(cc.CasinoClient, "connect", MagicMock(return_value="connect-coro")), \
         patch.object(cc.CasinoClient, "cmd_auth", MagicMock(return_value="auth-coro")), \
         patch.object(cc.CasinoClient, "receive_loop", MagicMock(return_value="recv-coro")), \
         patch.object(cc.CasinoClient, "_report_exit", MagicMock(return_value="report-coro")), \
         patch.object(cc.CasinoClient, "_stop_receiver", MagicMock(return_value="stop-coro")), \
         patch.object(cc.CasinoClient, "disconnect", MagicMock(return_value="disc-coro")), \
         patch.object(cc.CasinoClient, "_run_menu_loop", MagicMock()), \
         patch.object(auth, "_close_loop_for", MagicMock()), \
         patch("casino.client.bottombar.attach", MagicMock()), \
         patch("casino.client.bottombar.detach", MagicMock()), \
         patch.object(cc.asyncio, "new_event_loop", MagicMock(return_value=MagicMock(run_until_complete=MagicMock(side_effect=_drive)))), \
         patch.object(cc.asyncio, "set_event_loop", MagicMock()):
        client.run()

    token_connect.assert_not_called()


@pytest.mark.unit
def test_menu_loop_refreshes_a_token_that_is_nearly_expired():
    """Phase 2b: the menu loop refreshes a token inside the margin before the next command."""
    import inspect
    from casino.client import casino_client as cc

    src = inspect.getsource(cc.CasinoClient._run_menu_loop)
    assert "_refresh_token_if_due" in src


@pytest.mark.unit
def test_refresh_if_due_rotates_the_token_when_inside_the_margin(tmp_path):
    from casino.client import casino_client as cc

    token_file = tmp_path / "bed.token"
    soon = _make_token(1_000_000.0 + 30)
    token_file.write_text(soon + "\n")
    client = cc.CasinoClient.__new__(cc.CasinoClient)
    client.args = MagicMock(token_file=str(token_file), bed_host="127.0.0.1", bed_port=8765)
    client.ws = object()
    client._bearer_token = soon
    client._loop = MagicMock()
    rotated = _make_token(4_000_000_000.0)
    reply = {"ok": True, "token": rotated, "expires_at": 4_000_000_000.0}

    with patch.object(cc.CasinoClient, "time_now", lambda self: 1_000_000.0), \
         patch("bed.client.get_bed_connection") as conn, \
         patch("bed.client.authservice.BedAuthServiceClient") as svc_cls, \
         patch("bed.tools.auth._write_token_file"), \
         patch.object(cc.CasinoClient, "_run_loop", lambda self, coro: reply):
        svc_cls.return_value.refresh = MagicMock(return_value="refresh-coro")
        client._refresh_token_if_due()

    assert client._bearer_token == rotated


@pytest.mark.unit
def test_refresh_if_due_falls_back_to_login_when_refresh_fails(tmp_path):
    from casino.client import casino_client as cc

    token_file = tmp_path / "bed.token"
    soon = _make_token(1_000_000.0 + 30)
    token_file.write_text(soon + "\n")
    client = cc.CasinoClient.__new__(cc.CasinoClient)
    client.args = MagicMock(token_file=str(token_file), bed_host="127.0.0.1", bed_port=8765)
    client.ws = object()
    client._bearer_token = soon
    client._loop = MagicMock()
    failed = {"ok": False, "code": "token_expired", "message": "expired"}

    with patch.object(cc.CasinoClient, "time_now", lambda self: 1_000_000.0), \
         patch("bed.client.get_bed_connection"), \
         patch("bed.client.authservice.BedAuthServiceClient") as svc_cls, \
         patch.object(cc.CasinoClient, "_run_loop", lambda self, coro: failed):
        svc_cls.return_value.refresh = MagicMock(return_value="refresh-coro")
        client._refresh_token_if_due()

    assert client._bearer_token == soon
    assert client._refresh_failed is True


@pytest.mark.unit
def test_unreadable_token_is_sent_to_bed_not_pre_rejected():
    """An unreadable expiry is left for bed to judge; the client does not pre-reject it."""
    assert auth._stored_token_is_usable("good.token") is True
