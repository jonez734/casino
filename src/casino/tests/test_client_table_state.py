"""The client stores the server's casino_table_state in its table fields.

The server pushes casino_table_state on join and leave. The client keeps the table and its type in
current_table_moniker and current_table_game_type, the same fields its join reply already filled, so
the menu and table verbs read one source.
"""

import argparse
import asyncio

import pytest

from casino.client import CasinoClient


pytestmark = pytest.mark.unit


def _client():
    args = argparse.Namespace(bed_host="localhost", bed_port=8765, bed_path="/")
    return CasinoClient(args)


def _handle(client, msg):
    asyncio.run(client.handle_message(msg))


def test_seated_push_sets_the_table_and_its_type():
    c = _client()
    _handle(c, {"type": "casino_table_state", "moniker": "poker-a", "game_type": "poker", "seated": True})
    assert c.current_table_moniker == "poker-a"
    assert c.current_table_game_type == "poker"


def test_unseated_push_clears_the_table_and_its_type():
    c = _client()
    _handle(c, {"type": "casino_table_state", "moniker": "poker-a", "game_type": "poker", "seated": True})
    _handle(c, {"type": "casino_table_state", "moniker": None, "game_type": None, "seated": False})
    assert c.current_table_moniker is None
    assert c.current_table_game_type is None


def test_a_type_change_is_applied_from_the_push():
    c = _client()
    _handle(c, {"type": "casino_table_state", "moniker": "t1", "game_type": "blackjack", "seated": True})
    _handle(c, {"type": "casino_table_state", "moniker": "t1", "game_type": "poker", "seated": True})
    assert c.current_table_game_type == "poker"


def test_left_table_reply_clears_the_table_even_without_the_push():
    c = _client()
    _handle(c, {"type": "casino_table_state", "moniker": "blackjack-a", "game_type": "blackjack", "seated": True})
    _handle(c, {"type": "left_table", "moniker": "blackjack-a", "message": "left"})
    assert c.current_table_moniker is None
    assert c.current_table_game_type is None
