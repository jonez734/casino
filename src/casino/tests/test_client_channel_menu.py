#!/usr/bin/env python3
# casino/tests/test_client_channel_menu.py
# The E option opens the channel submenu: subscribe, unsubscribe, list. The submenu sends
# subscribe_channel / unsubscribe_channel / get_subscriptions, and the client prints the
# subscribed / unsubscribed / subscriptions replies. No daemon: the socket send is stubbed.

from unittest.mock import MagicMock, patch

import pytest

from casino.client import casino_client as cc
from casino.client import menu


def _close_coro(coro):
    """Close a coroutine handed to the mocked loop so it is not left unawaited."""
    if hasattr(coro, "close"):
        coro.close()
    return None


def _client():
    client = cc.CasinoClient.__new__(cc.CasinoClient)
    client.current_table_moniker = None
    client._loop = MagicMock()
    client._loop.run_until_complete.side_effect = _close_coro
    client.send = MagicMock(side_effect=lambda msg: _close_coro(msg))
    return client


def _run_submenu(client, choices, answers=()):
    """Drive cmd_channels_menu with scripted submenu choices and channel-name answers."""
    echoes = []
    choice_iter = iter(choices)
    answer_iter = iter(answers)
    with patch.object(cc.io, "inputchoice", side_effect=lambda *a, **k: next(choice_iter)), \
         patch.object(cc.io, "inputstring", side_effect=lambda *a, **k: next(answer_iter)), \
         patch.object(cc.io, "echo", side_effect=lambda *a, **k: echoes.append(str(a[0]) if a else "")):
        client.cmd_channels_menu()
    return echoes


@pytest.mark.unit
def test_menu_offers_channels_as_e():
    letters = [letter for letter, _label in menu._visible_options(None)]
    assert "e" in letters


@pytest.mark.unit
def test_subscribe_sends_subscribe_channel_with_typed_name():
    client = _client()
    _run_submenu(client, choices=["s", "q"], answers=["casino:table:poker-1:chat"])
    sent = [c.args[0] for c in client.send.call_args_list]
    assert {"type": "subscribe_channel", "channel": "casino:table:poker-1:chat"} in sent


@pytest.mark.unit
def test_unsubscribe_sends_unsubscribe_channel_with_typed_name():
    client = _client()
    _run_submenu(client, choices=["u", "q"], answers=["casino:table:poker-1:events"])
    sent = [c.args[0] for c in client.send.call_args_list]
    assert {"type": "unsubscribe_channel", "channel": "casino:table:poker-1:events"} in sent


@pytest.mark.unit
def test_list_sends_get_subscriptions():
    client = _client()
    _run_submenu(client, choices=["l", "q"])
    sent = [c.args[0] for c in client.send.call_args_list]
    assert {"type": "get_subscriptions"} in sent


@pytest.mark.unit
def test_empty_channel_name_sends_nothing():
    client = _client()
    echoes = _run_submenu(client, choices=["s", "q"], answers=[""])
    assert client.send.call_count == 0
    assert any("channel name required" in e for e in echoes)


@pytest.mark.unit
def test_quit_returns_without_sending():
    client = _client()
    _run_submenu(client, choices=["q"])
    assert client.send.call_count == 0


@pytest.mark.unit
def test_subscribed_reply_is_printed():
    client = _client()
    echoes = []
    with patch.object(cc.io, "echo", side_effect=lambda *a, **k: echoes.append(str(a[0]))):
        import asyncio
        asyncio.run(client.handle_message({"type": "subscribed", "channel": "casino:table:poker-1:chat"}))
    assert any("Subscribed: casino:table:poker-1:chat" in e for e in echoes)


@pytest.mark.unit
def test_unsubscribed_reply_is_printed():
    client = _client()
    echoes = []
    with patch.object(cc.io, "echo", side_effect=lambda *a, **k: echoes.append(str(a[0]))):
        import asyncio
        asyncio.run(client.handle_message({"type": "unsubscribed", "channel": "casino:table:poker-1:chat"}))
    assert any("Unsubscribed: casino:table:poker-1:chat" in e for e in echoes)


@pytest.mark.unit
def test_subscriptions_reply_lists_channels_sorted():
    client = _client()
    echoes = []
    with patch.object(cc.io, "echo", side_effect=lambda *a, **k: echoes.append(str(a[0]))):
        import asyncio
        asyncio.run(client.handle_message({"type": "subscriptions", "channels": ["b:chan", "a:chan"]}))
    lines = [e.strip() for e in echoes]
    assert "a:chan" in lines and "b:chan" in lines
    assert lines.index("a:chan") < lines.index("b:chan")


@pytest.mark.unit
def test_empty_subscriptions_reply_says_none():
    client = _client()
    echoes = []
    with patch.object(cc.io, "echo", side_effect=lambda *a, **k: echoes.append(str(a[0]))):
        import asyncio
        asyncio.run(client.handle_message({"type": "subscriptions", "channels": []}))
    assert any("No channel subscriptions" in e for e in echoes)


@pytest.mark.unit
def test_watching_table_reply_is_printed_not_debug():
    """The server answers a watch with watching_table; it must print, not fall through to debug."""
    import asyncio

    client = _client()
    echoes = []
    with patch.object(cc.io, "echo", side_effect=lambda *a, **k: echoes.append((str(a[0]), k.get("level")))):
        asyncio.run(client.handle_message({"type": "watching_table", "moniker": "poker-1", "message": "Now watching table poker-1"}))
    assert ("Now watching table poker-1", None) in echoes
    assert not any(level == "debug" for _text, level in echoes)
