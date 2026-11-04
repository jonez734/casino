"""casino_table_state: one message shape, defined in api/messages.py, used by every game.

Every game's seat change pushes the same message, so the client reads one shape for all of them.
"""

import pytest

from casino.api import messages
from casino.api.messages import MessageType, table_state_message


pytestmark = pytest.mark.unit


def test_the_type_is_named_casino_table_state():
    assert MessageType.CASINO_TABLE_STATE.value == "casino_table_state"


def test_seated_message_carries_the_table_and_type():
    assert table_state_message(moniker="poker-a", game_type="poker", seated=True) == {
        "type": "casino_table_state", "moniker": "poker-a", "game_type": "poker", "seated": True,
    }


def test_unseated_message_has_no_table():
    assert table_state_message(moniker=None, game_type=None, seated=False) == {
        "type": "casino_table_state", "moniker": None, "game_type": None, "seated": False,
    }


def test_seated_is_a_plain_bool():
    assert table_state_message(moniker="t", game_type="g", seated=1)["seated"] is True


def test_api_handler_reuses_the_messages_builder():
    from casino.api import handler

    assert handler.table_state_message is messages.table_state_message
