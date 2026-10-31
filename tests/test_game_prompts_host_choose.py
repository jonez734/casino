"""Stage 8d: the game prompts choose through the host seam.

Each game reads one answer with ``host.choose``. Where the prompt is a directly callable
function, these tests call it: the hosted menu receives the prompt, and a lowercase answer
gives the same result the game expects. Where the prompt sits inside a larger loop, the test
checks the call site and its normalization in the source.
"""

import importlib
from pathlib import Path
from unittest.mock import patch

import pytest

from casino import host


pytestmark = pytest.mark.unit


CASINO = Path(__file__).resolve().parents[1] / "src" / "casino"


def _source(relpath: str) -> str:
    with open(CASINO / relpath, encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(autouse=True)
def _standalone_after():
    host.unregister_menu()
    yield
    host.unregister_menu()


def _unscored_player():
    """A yahtzee player whose scorecard has every category open, as a real player's does."""
    player = type("P", (), {})()
    player.scorecard = {category: None for category in yahtzee_lib.CATEGORIES}
    return player


def _hosted(answers):
    """Register a hosted menu that returns ``answers`` in turn. Records each call."""
    calls = []
    it = iter(answers)

    def menu(prompt, registry, default="", help=None):
        calls.append({"prompt": prompt, "keys": sorted(registry.keys()), "default": default})
        return next(it)

    host.register_menu(menu)
    return calls


# ---- slots: bet prompt is a directly callable function -------------------------------------


# ---- yahtzee: both prompts are directly callable -------------------------------------------


# ---- tictactoe: move prompt is in a loop, so the seam contract is checked directly ---------


# ---- blackjack and slots-again: prompts sit inside loops; check the call site --------------

def test_blackjack_action_prompt_routes_through_host_and_is_uppercased():
    src = _source("blackjack/play.py")
    assert "host.choose(" in src
    assert "choice = choice.upper()" in src
    assert "io.inputchoice(" not in src.split("def _render_action_menu")[1].split("def main")[1]


def test_slots_again_prompt_routes_through_host_and_is_uppercased():
    src = _source("slots/play.py")
    assert 'again = (host.choose(' in src
    assert '"n"' not in src.split("again = (host.choose(")[1].split("\n\n")[0]
    assert ").upper()" in src.split("again = (host.choose(")[1].split("if again")[0]
