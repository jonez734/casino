"""Stage 8b: client submenus choose through the host seam.

Covers, for the channel submenu, the bank submenu, and the bank source picker:
  - when hosted, the menu key comes from the registered host menu (lowercase, as stored);
  - the submenu compares on lowercase, so hosted and standalone behave the same;
  - the bank source picker's default still applies on an empty answer.
Standalone uses io.inputchoice and is covered by the existing submenu tests.
"""

from unittest.mock import MagicMock, patch

import pytest

from casino import host
from casino.client import casino_client as cc


pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _standalone_after():
    host.unregister_menu()
    yield
    host.unregister_menu()


def _close_coro(coro):
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


def _hosted_keys(keys):
    """Register a hosted menu that returns ``keys`` in turn, keys as stored (lowercase).
    Returns the list of calls it received, for asserting arguments."""
    calls = []
    it = iter(keys)

    def menu(prompt, registry, default="", help=None):
        calls.append({"keys": sorted(registry.keys()), "default": default})
        return next(it)

    host.register_menu(menu)
    return calls


def test_channels_submenu_hosted_quits_on_lowercase_q():
    calls = _hosted_keys(["q"])
    client = _client()
    with patch.object(cc.io, "echo"):
        client.cmd_channels_menu()
    assert calls and calls[0]["keys"] == ["l", "q", "s", "u"]
    assert calls[0]["default"] == "q"


def test_channels_submenu_hosted_runs_the_chosen_action_once():
    """'l' lists subscriptions (one send), then 'q' quits. Lowercase, as LO returns it."""
    _hosted_keys(["l", "q"])
    client = _client()
    with patch.object(cc.io, "echo"):
        client.cmd_channels_menu()
    msgs = [c.args[0] for c in client.send.call_args_list]
    assert msgs == [{"type": "get_subscriptions"}]


def test_bank_menu_hosted_quits_on_lowercase_q():
    calls = _hosted_keys(["q"])
    client = _client()
    with patch.object(cc.io, "echo"):
        client.cmd_bank_menu()
    assert calls and calls[0]["keys"] == ["a", "b", "h", "l", "p", "q", "t", "w"]
    assert calls[0]["default"] == "q"


def test_bank_menu_hosted_balance_then_quit():
    """'b' runs cmd_bank_balance (a send), then 'q' quits."""
    _hosted_keys(["b", "q"])
    client = _client()
    with patch.object(cc.io, "echo"), \
         patch.object(cc.CasinoClient, "cmd_bank_balance", create=True) as bal:
        client.cmd_bank_menu()
    bal.assert_called_once()


def test_bank_source_hosted_returns_house_for_lowercase_h():
    _hosted_keys(["h"])
    client = _client()
    with patch.object(cc.io, "inputstring", return_value="alice"), \
         patch.object(cc.io, "inputinteger", return_value=5), \
         patch.object(cc.io, "echo"):
        client.cmd_bank_add()
    sent = client.send.call_args.args[0]
    assert sent["source"] == "house"


def test_bank_source_hosted_returns_player_for_lowercase_p():
    _hosted_keys(["p"])
    client = _client()
    with patch.object(cc.io, "inputstring", return_value="alice"), \
         patch.object(cc.io, "inputinteger", return_value=5), \
         patch.object(cc.io, "echo"):
        client.cmd_bank_add()
    sent = client.send.call_args.args[0]
    assert sent["source"] == "player"


def test_bank_source_hosted_default_is_house():
    calls = _hosted_keys(["h"])
    client = _client()
    with patch.object(cc.io, "inputstring", return_value="alice"), \
         patch.object(cc.io, "inputinteger", return_value=5), \
         patch.object(cc.io, "echo"):
        client.cmd_bank_add()
    assert calls[0]["default"] == "h"
    assert sorted(calls[0]["keys"]) == ["h", "p"]
