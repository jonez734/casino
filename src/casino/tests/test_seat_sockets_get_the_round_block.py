"""A seat's own sockets get the settled round as well as its hands, so the second window matches the playing window.

The per-seat fan-out sent each seat its state without the round block, so a second window showed a hand with a result
but no round net. Each seat's view now carries the round, with that seat's own net.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from casino.api import handler as h
from casino.api.payloads import GameState


pytestmark = pytest.mark.unit


class _Sink:
    def __init__(self):
        self.sent = []

    async def send_to_session(self, connection_id, message):
        self.sent.append((connection_id, message))


def test_a_seats_sockets_receive_the_round_block_with_their_own_net(monkeypatch):
    obj = h.GameServiceHandler.__new__(h.GameServiceHandler)
    obj.args = SimpleNamespace()
    obj.game_service = MagicMock()
    obj.game_service._pool = None
    obj.game_service.get_game_state.return_value = GameState.from_dict({"table_moniker": "t", "phase": "settled",
                                                                       "hands": []})
    obj.sessions = SimpleNamespace(sessions_for_moniker=lambda m: ["conn-jam-1", "conn-jam-2"] if m == "jam" else [])
    from casino.dal import table as dal_table
    monkeypatch.setattr(dal_table, "seated_monikers", lambda *a, **k: ["jam"])
    settled = {"dealer_total": 18, "dealer_cards": ["QC", "8D"], "net": -2, "outcomes": [
        {"player": "jam", "net": -2, "result": "loss", "text": "you 16, dealer 18, net -2",
         "others_text": "jam 16, dealer 18, net -2"},
    ]}
    sink = _Sink()
    asyncio.run(obj._send_each_seat_its_state(sink, "t", settled=settled))
    assert {cid for cid, _ in sink.sent} == {"conn-jam-1", "conn-jam-2"}
    for _, message in sink.sent:
        assert message["round_settled"]["net"] == -2
        assert message["round_settled"]["outcomes"][0]["text"] == "you 16, dealer 18, net -2"
