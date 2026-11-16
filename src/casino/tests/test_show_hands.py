"""``show_hands`` returns the requesting player's own game state (their hands), without dealing.

A player who has lost the screen (or whose bet was refused) can ask to see their hands again. The reply is their
own view; asking never draws a card.
"""

import argparse
import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from casino.api import handler as h
from casino.api.payloads import GameState


pytestmark = pytest.mark.unit


def _router(state_dict, *, seated_table="blackjack-jam"):
    obj = h.TableServiceHandler.__new__(h.TableServiceHandler)
    obj.args = SimpleNamespace()
    obj._pool = None
    obj.game_service = MagicMock()
    obj.game_service.get_game_state = MagicMock(return_value=GameState.from_dict(state_dict))
    obj.sessions = SimpleNamespace(get_table_moniker=lambda sid: seated_table)
    obj._check_access = lambda websocket, op, message: (SimpleNamespace(moniker="jam"), None)
    return obj


def test_show_hands_returns_the_players_own_state_without_dealing():
    state = {"table_moniker": "blackjack-jam", "phase": "playing", "player_hand": ["8D", "QC"], "hands": []}
    obj = _router(state)
    reply = asyncio.run(obj._handle_show_hands(SimpleNamespace(id=1), {"type": "show_hands"}))
    assert reply["type"] == "game_state"
    assert reply["player_hand"] == ["8D", "QC"]
    obj.game_service.get_game_state.assert_called_once_with("blackjack-jam", "jam", deal=False)


def test_show_hands_with_no_seat_is_refused():
    obj = _router({}, seated_table=None)
    reply = asyncio.run(obj._handle_show_hands(SimpleNamespace(id=1), {"type": "show_hands"}))
    assert reply == {"type": "error", "code": "not_at_table", "message": "You are not seated at a table."}
    obj.game_service.get_game_state.assert_not_called()


def test_show_hands_finds_the_seat_the_join_recorded():
    # The join records the seat through the websocket (_set_seated), so show_hands must read it the same way.
    state = {"table_moniker": "blackjack-jam", "phase": "playing", "player_hand": ["8D", "QC"], "hands": []}
    obj = _router(state, seated_table=None)
    obj._get_seated = lambda websocket: "blackjack-jam"
    reply = asyncio.run(obj._handle_show_hands(SimpleNamespace(id=1), {"type": "show_hands"}))
    assert reply["type"] == "game_state"
    assert reply["player_hand"] == ["8D", "QC"]


def test_show_hands_uses_the_database_seat_when_the_session_has_none():
    # The session copy of the seat can be empty while the database still seats the player (the journal showed
    # seated=None for a seated player). The seat is read from the database, as the access check reads it.
    state = {"table_moniker": "blackjack-jam", "phase": "playing", "player_hand": ["8D", "QC"], "hands": []}
    obj = _router(state, seated_table=None)
    obj._get_seated = lambda websocket: None
    from casino import access as access_mod
    from unittest.mock import patch
    with patch.object(access_mod, "_seated_table", return_value="blackjack-jam"):
        reply = asyncio.run(obj._handle_show_hands(SimpleNamespace(id=1), {"type": "show_hands"}))
    assert reply["type"] == "game_state"
    assert reply["player_hand"] == ["8D", "QC"]
