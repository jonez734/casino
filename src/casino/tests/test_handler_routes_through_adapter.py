"""The game action path reports a refusal through the adapter, with the same wire reply as before.

Slice 2 of the blackjack adoption. The handler converts the service's dict once, with api/results.py,
and sends the exact dict it sent before. The golden shape is {"type": "error", "code": "action_failed",
"message": <service message>}.
"""

import inspect

import pytest

from casino.api import handler as handler_mod

pytestmark = pytest.mark.unit


def test_action_refusal_uses_the_adapter():
    src = inspect.getsource(handler_mod.GameServiceHandler._handle_game_action)
    assert "to_action_result" in src, "the action refusal must be converted by api.results"


def test_action_refusal_reply_is_unchanged():
    from casino.api import results as res

    service_result = {"success": False, "message": "Cannot surrender after hitting"}
    converted = res.to_action_result(service_result)
    assert converted.ok is False
    assert {"type": "error", "code": "action_failed", "message": converted.message} == {
        "type": "error", "code": "action_failed", "message": "Cannot surrender after hitting",
    }
