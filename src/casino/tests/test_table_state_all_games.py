"""casino_table_state reaches the player's session for every game's seat change.

Poker join and leave, yahtzee and tictactoe seating, and a reconnect while seated all push the same
message shape. Each push goes to that session only.
"""

import asyncio
import json
from types import SimpleNamespace

import pytest

from casino.api.messages import send_table_state


pytestmark = pytest.mark.unit


class Sock:
    def __init__(self, ident=1):
        self.id = ident
        self.sent = []

    async def send(self, text):
        self.sent.append(json.loads(text))


def test_send_table_state_sends_the_shared_shape_to_one_session():
    mine, other = Sock(1), Sock(2)
    asyncio.run(send_table_state(mine, moniker="poker-a", game_type="poker", seated=True))
    assert mine.sent == [{"type": "casino_table_state", "moniker": "poker-a",
                          "game_type": "poker", "seated": True}]
    assert other.sent == []


def test_send_table_state_failure_is_not_raised():
    class Dead:
        async def send(self, text):
            raise RuntimeError("socket closed")

    asyncio.run(send_table_state(Dead(), moniker=None, game_type=None, seated=False))


@pytest.mark.parametrize("game_type", ["poker", "yahtzee", "tictactoe"])
def test_each_game_seats_with_its_own_type(game_type):
    sock = Sock(1)
    asyncio.run(send_table_state(sock, moniker=f"{game_type}-t", game_type=game_type, seated=True))
    assert sock.sent[0]["game_type"] == game_type
    assert sock.sent[0]["seated"] is True


def test_resumed_seat_pushes_the_table_and_its_type(monkeypatch):
    from casino.api import handler as h
    from casino.dal import table as dal_table

    monkeypatch.setattr(dal_table, "get_table", lambda *a, **k: {"moniker": "bj-a", "type": "blackjack"})
    obj = h.AuthService.__new__(h.AuthService)
    obj.args = SimpleNamespace()
    obj._pool = None
    obj.sessions = SimpleNamespace(get_table_moniker=lambda sid: "bj-a")
    sock = Sock(1)
    asyncio.run(obj._push_resumed_seat(sock, 1))
    assert sock.sent == [{"type": "casino_table_state", "moniker": "bj-a",
                          "game_type": "blackjack", "seated": True}]


def test_unseated_session_gets_no_resumed_push():
    from casino.api import handler as h

    obj = h.AuthService.__new__(h.AuthService)
    obj.args = SimpleNamespace()
    obj._pool = None
    obj.sessions = SimpleNamespace(get_table_moniker=lambda sid: None)
    sock = Sock(1)
    asyncio.run(obj._push_resumed_seat(sock, 1))
    assert sock.sent == []
