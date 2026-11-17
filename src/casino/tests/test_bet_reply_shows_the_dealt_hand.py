"""The bettor's reply to a bet carries the dealt hand, including when the dealer has a natural.

A bet's own reply is the player's game_state. It must show the hand and the dealer's cards straight away, so the
player does not have to run 'game hands' to see what happened.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from casino.api import handler as h
from casino.api.payloads import GameState


pytestmark = pytest.mark.unit


def _bet_handler(state_dict):
    obj = h.BetServiceHandler.__new__(h.BetServiceHandler)
    obj.args = SimpleNamespace()
    obj._pool = None
    obj.game_service = MagicMock()
    obj.game_service.place_bet.return_value = {"success": True}
    obj.game_service.get_game_state.return_value = GameState.from_dict(state_dict)
    obj.game_service.take_settled_round.return_value = None
    obj._check_access = lambda websocket, op, message: (SimpleNamespace(moniker="alice", table_moniker="blackjack-jam",
                                                                         is_sysop=False), None)
    obj._legacy_session_id = lambda websocket: 1
    obj._drain_round_events = lambda: None
    obj._get_observers = lambda table: set()
    obj._get_player_count = lambda table: 1
    obj.sessions = SimpleNamespace(get_table_moniker=lambda sid: "blackjack-jam")
    async def _noop(*a, **k):
        return None

    obj._send_to_watchers = _noop
    obj._send_each_seat_its_state = _noop
    obj._publish_to_table = _noop
    return obj


def test_a_bet_reply_carries_the_dealt_hand_and_dealer_cards(monkeypatch):
    import asyncio
    import json

    state = {"table_moniker": "blackjack-jam", "phase": "settled",
             "player_hand": ["KH", "5C"], "player_total": 15,
             "dealer_hand": ["AC", "JC"], "dealer_total": 21, "hands": []}
    obj = _bet_handler(state)
    sent = []

    class _Socket:
        id = "c1"

        async def send(self, text):
            sent.append(json.loads(text))

    from casino.dal import table as dal_table
    monkeypatch.setattr(dal_table, "seated_monikers", lambda *a, **k: [])
    asyncio.run(obj._handle_bet(_Socket(), {"type": "bet", "amount": 10}, server=object()))
    assert sent, "the bettor is sent a reply"
    assert sent[0]["player_hand"] == ["KH", "5C"]
    assert sent[0]["dealer_hand"] == ["AC", "JC"]
