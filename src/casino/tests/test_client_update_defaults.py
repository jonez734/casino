#!/usr/bin/env python3
# casino/tests/test_client_update_defaults.py
# The update command shows each table field's current value as its prompt default, and
# sends only the fields that changed. Source-level plus a stubbed prompt run; no daemon.

import inspect
from unittest.mock import MagicMock, patch

from casino.client import casino_client as cc


def _src():
    return inspect.getsource(cc.CasinoClient.cmd_update_table)


def test_update_fetches_the_table_before_prompting():
    src = _src()
    assert "self._fetch_table(moniker)" in src
    assert src.index("_fetch_table") < src.index("inputinteger")


def test_min_and_max_bet_prompts_use_the_current_value_as_default():
    src = _src()
    assert "oldvalue=cur_min" in src
    assert "oldvalue=cur_max" in src


def test_status_prompt_uses_the_current_value_as_default():
    assert "str(cur_status)" in _src()


def test_update_sends_only_changed_fields():
    import asyncio

    client = cc.CasinoClient.__new__(cc.CasinoClient)
    client._loop = asyncio.new_event_loop()
    sent = []

    async def _record(msg):
        sent.append(msg)

    client.send = _record
    table = {"min_bet": 10, "max_bet": 500, "status": "open"}
    client._fetch_table = lambda moniker, timeout=5.0: table
    # user keeps min (10), changes max to 900, keeps status open
    answers = iter(["t1"])
    with patch.object(cc.io, "inputstring", side_effect=lambda *a, **k: next(answers, "open")), \
         patch.object(cc.io, "inputinteger", side_effect=[10, 900]), \
         patch.object(cc.io, "echo"):
        # Drive the real coroutine (send) to completion on a private loop.
        try:
            client.cmd_update_table()
        finally:
            client._loop.close()
    assert len(sent) == 1
    assert sent[0] == {"type": "casino_update_table", "moniker": "t1", "max_bet": 900}


def test_update_with_no_changes_sends_nothing():
    client = cc.CasinoClient.__new__(cc.CasinoClient)
    client._loop = MagicMock()
    sent = []
    client.send = lambda msg: sent.append(msg)
    client._fetch_table = lambda moniker, timeout=5.0: {"min_bet": 10, "max_bet": 500, "status": "open"}
    with patch.object(cc.io, "inputstring", side_effect=["t1", "open"]), \
         patch.object(cc.io, "inputinteger", side_effect=[10, 500]), \
         patch.object(cc.io, "echo"):
        client._loop.run_until_complete = lambda coro: None
        client.cmd_update_table()
    assert sent == []


def test_missing_table_is_reported_and_nothing_is_sent():
    client = cc.CasinoClient.__new__(cc.CasinoClient)
    client._loop = MagicMock()
    sent = []

    async def _record(msg):
        sent.append(msg)

    client.send = _record
    client._fetch_table = lambda moniker, timeout=5.0: None
    with patch.object(cc.io, "inputstring", side_effect=["nope"]), \
         patch.object(cc.io, "echo") as echo:
        client.cmd_update_table()
    assert sent == []
    assert any("No table named nope" in str(c.args[0]) for c in echo.call_args_list)
