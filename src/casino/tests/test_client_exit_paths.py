#!/usr/bin/env python3
# casino/tests/test_client_exit_paths.py
# CasinoClient.run() handles Ctrl-D (EOF) and Ctrl-C (INTR) without a traceback, records the
# exit reason, and always runs cleanup. Stubbed: no daemon, no terminal.

import asyncio
import inspect
from unittest.mock import MagicMock, patch

import pytest

from casino.client import casino_client as cc
from casino import __main__ as cm


def _drive(coro_or_value, result=True):
    """Run a coroutine to completion if one was given, so the stub loop leaves nothing unawaited.

    Closing a coroutine would skip it: the exit report and receiver stop would then never run.
    """
    if hasattr(coro_or_value, "send"):
        # asyncio.run uses its own loop, so this never re-enters the mocked _loop below.
        return asyncio.run(_await(coro_or_value))
    return result


async def _await(coro):
    return await coro


def _client():
    client = cc.CasinoClient.__new__(cc.CasinoClient)
    client._loop = MagicMock()
    client._loop.run_until_complete = MagicMock(side_effect=lambda c: _drive(c))
    client.authenticated = True
    client._receive_task = None
    client._bearer_token = None
    client.ws = None
    client.moniker = ""
    client._close_code = None  # set by receive() when the socket closes; None when it did not
    client.disconnect = MagicMock(return_value="disconnect-coro")
    client.connect = MagicMock(return_value="connect-coro")
    client.cmd_auth = MagicMock(return_value="auth-coro")
    client.receive_loop = MagicMock(return_value="recv-coro")
    # The exit report and receiver stop are covered directly in test_client_exit_report.py.
    # Here they are plain stubs, so run() never creates a coroutine nothing awaits.
    client._report_exit = MagicMock(return_value=False)
    client._stop_receiver = MagicMock(return_value=None)
    client.args = MagicMock(token_file=None)
    return client


def _run(client, menu_exc):
    with patch.object(cc.CasinoClient, "_run_menu_loop", side_effect=menu_exc), \
         patch("asyncio.new_event_loop", return_value=client._loop), \
         patch("asyncio.set_event_loop"), \
         patch("casino.auth._close_loop_for") as close_loop, \
         patch.object(cc.io, "echo") as echo, \
         patch("casino.client.bottombar.attach"), \
         patch("casino.client.bottombar.detach"):
        client.run()
    return close_loop, echo


def test_eof_is_a_clean_exit_with_reason_eof():
    client = _client()
    close_loop, echo = _run(client, EOFError)
    assert client._exit_reason == "eof"
    assert any("EOF" in str(c.args[0]) for c in echo.call_args_list)
    close_loop.assert_called_once_with(client)


def test_interrupt_is_a_clean_exit_with_reason_intr():
    client = _client()
    close_loop, echo = _run(client, KeyboardInterrupt)
    assert client._exit_reason == "intr"
    assert any("INTR" in str(c.args[0]) for c in echo.call_args_list)
    close_loop.assert_called_once_with(client)


def test_normal_quit_records_reason_quit():
    client = _client()
    close_loop, _ = _run(client, None)
    assert client._exit_reason == "quit"
    close_loop.assert_called_once_with(client)


def test_cleanup_runs_even_when_the_menu_raises_an_error():
    client = _client()
    with pytest.raises(RuntimeError):
        _run(client, RuntimeError("boom"))
    assert client._exit_reason == "error"
    client._loop.run_until_complete.assert_called()  # disconnect was driven


def test_auth_failure_before_the_menu_records_auth_failed():
    client = _client()
    client.connect = MagicMock(return_value="connect-coro")
    client._loop.run_until_complete = MagicMock(return_value=False)
    with patch("asyncio.new_event_loop", return_value=client._loop), \
         patch("asyncio.set_event_loop"), \
         patch("casino.auth._close_loop_for") as close_loop:
        client.run()
    assert client._exit_reason == "auth_failed"
    close_loop.assert_called_once_with(client)


def test_run_wraps_the_whole_body_in_try_with_cleanup_in_finally():
    src = inspect.getsource(cc.CasinoClient.run)
    outer_try = src.index("        try:\n            token_path")
    assert outer_try < src.index("        except EOFError:")
    # The outer finally is the last one; cleanup lives there, after the excepts.
    outer_finally = src.rindex("        finally:")
    assert src.index("        except EOFError:") < outer_finally
    tail = src[outer_finally:]
    assert "disconnect()" in tail
    assert "_close_loop_for(self)" in tail


def test_run_bed_returns_zero_for_a_clean_stop_after_login():
    args = MagicMock(token_file=None)
    with patch.object(cm, "CasinoClient") as Client, patch.object(cm, "locale"), patch.object(cm, "time"):
        inst = Client.return_value
        inst.authenticated = True
        inst._exit_reason = "eof"
        assert cm._run_bed(args) == 0


def test_run_bed_returns_one_when_auth_never_succeeded():
    args = MagicMock(token_file=None)
    with patch.object(cm, "CasinoClient") as Client, patch.object(cm, "locale"), patch.object(cm, "time"):
        inst = Client.return_value
        inst.authenticated = False
        inst._exit_reason = "auth_failed"
        assert cm._run_bed(args) == 1
