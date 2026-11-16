"""``game hands`` asks the server for the player's own hands and shows them again.

It sends a ``show_hands`` request; the reply is an ordinary ``game_state``, rendered like the one after a bet.
"""

import argparse
from unittest.mock import MagicMock, patch

import pytest

from casino.client import CasinoClient
from casino.client import menu as m


pytestmark = pytest.mark.unit


def test_the_game_menu_offers_hands():
    assert "hands" in m._GAME_SUBS


def test_game_hands_sends_show_hands():
    import asyncio

    client = CasinoClient(argparse.Namespace(bed_host="127.0.0.1", bed_port=8765, bed_path="/"))
    client._loop = asyncio.new_event_loop()
    try:
        async def _sent(message):
            return None

        with patch.object(client, "send", side_effect=_sent) as send:
            client._dispatch_game("hands", None)
        sent = send.call_args.args[0]
        assert sent == {"type": "show_hands"}
    finally:
        client._loop.close()
