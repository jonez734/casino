"""``table leave`` keeps the seat until the server confirms the leave, and reports a refusal.

Before this, the client cleared its table the moment it sent ``leave_table``. A refused leave then left the
client showing no table while the server still held the seat, and a refusal with no text printed "Error: None".
Now the seat is cleared only by ``left_table``; a refusal keeps it and is reported with a message.
"""

import argparse
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from casino.client import CasinoClient


pytestmark = pytest.mark.unit


def _client():
    return CasinoClient(argparse.Namespace(bed_host="127.0.0.1", bed_port=8765, bed_path="/"))


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _client_on_a_loop(client):
    """Give the client its own loop, closed by ``_close``, so no loop leaks into a later test."""
    client._loop = asyncio.new_event_loop()
    return client


def _close(client):
    if client._loop is not None and not client._loop.is_closed():
        client._loop.close()


def test_a_refused_leave_keeps_the_seat_and_says_why():
    client = _client()
    client.current_table_moniker = "blackjack-jam"
    client.current_table_game_type = "blackjack"
    client = _client_on_a_loop(client)
    with patch.object(client, "send", AsyncMock()), \
         patch("casino.client.casino_client.io.echo") as echo:
        client.cmd_leave_table()
        _run(client.handle_message({"type": "error", "code": "not_at_table", "message": "Not at table"}))
    assert client.current_table_moniker == "blackjack-jam", "a refused leave keeps the client seated"
    printed = " ".join(str(c.args[0]) for c in echo.call_args_list)
    _close(client)
    assert "Not at table" in printed


def test_a_refusal_with_no_text_still_says_the_leave_failed():
    client = _client()
    client.current_table_moniker = "blackjack-jam"
    client = _client_on_a_loop(client)
    with patch.object(client, "send", AsyncMock()), \
         patch("casino.client.casino_client.io.echo") as echo:
        client.cmd_leave_table()
        _run(client.handle_message({"type": "error", "code": "not_at_table"}))
    printed = " ".join(str(c.args[0]) for c in echo.call_args_list)
    _close(client)
    assert "None" not in printed
    assert "leave" in printed.lower()


def test_a_confirmed_leave_clears_the_seat():
    client = _client()
    client.current_table_moniker = "blackjack-jam"
    client = _client_on_a_loop(client)
    with patch.object(client, "send", AsyncMock()):
        client.cmd_leave_table()
        _run(client.handle_message({"type": "left_table", "message": "Left table"}))
    _close(client)
    assert client.current_table_moniker is None
