# casino/tests/test_game_events_are_server_published.py
# Game events on a table's events channel are published by the server, with no player as the
# sender. With a sender, the announce-only check refuses the seated player's own table events
# (the player is not an announcer), and channel_publish drops them silently.

import re
from pathlib import Path

import casino

API = Path(casino.__file__).resolve().parent / "api" / "handler.py"
POKER = Path(casino.__file__).resolve().parent / "poker" / "api_handler.py"


def _function_body(text: str, name: str) -> str:
    start = text.index(f"def {name}(")
    nxt = re.search(r"\n    (async )?def |\nclass |\ndef ", text[start + 1:])
    return text[start: start + 1 + (nxt.start() if nxt else len(text))]


def test_cash_table_events_publish_without_a_sender():
    body = _function_body(API.read_text(encoding="utf-8"), "_publish_to_table")
    assert "sender_moniker=" not in body, "table events must be server-published (no sender)"


def test_poker_events_publish_without_a_sender():
    body = _function_body(POKER.read_text(encoding="utf-8"), "_publish_events")
    assert "sender_moniker=" not in body, "poker events must be server-published (no sender)"
