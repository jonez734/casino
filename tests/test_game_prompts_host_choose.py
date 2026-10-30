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

slots = importlib.import_module("casino.slots.play")
yahtzee = importlib.import_module("casino.yahtzee.play")
yahtzee_lib = importlib.import_module("casino.yahtzee.lib")
tt = importlib.import_module("casino.tictactoe.__main__")

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

def test_slots_bet_prompt_goes_through_host_and_quits_on_lowercase_q():
    calls = _hosted(["q"])
    player = type("P", (), {"min_bet": 1, "max_bet": 5, "credits": 10})()
    with patch.object(slots.io, "echo"):
        assert slots._prompt_bet(player) is None
    assert calls[0]["keys"] == ["b", "q"]
    assert calls[0]["default"] == "b"


# ---- yahtzee: both prompts are directly callable -------------------------------------------

def test_yahtzee_category_prompt_goes_through_host_and_returns_the_category():
    calls = _hosted(["a"])
    player = _unscored_player()
    with patch.object(yahtzee, "_show_scorecard"), patch.object(yahtzee.io, "echo"):
        category = yahtzee._prompt_score_category(player)
    assert calls[0]["keys"] == list("abcdefghijklm")
    assert calls[0]["default"] == "c"
    assert category == yahtzee_lib.CATEGORIES[0]


def test_yahtzee_category_prompt_accepts_uppercase_from_standalone():
    """Standalone io.inputchoice returns uppercase. The index step lowercases, so 'A' works."""
    player = _unscored_player()
    with patch.object(yahtzee, "_show_scorecard"), patch.object(yahtzee.io, "echo"), \
         patch.object(host.io, "inputchoice", return_value="A"):
        category = yahtzee._prompt_score_category(player)
    assert category == yahtzee_lib.CATEGORIES[0]


def test_yahtzee_action_prompt_goes_through_host():
    calls = _hosted(["s"])
    player = type("P", (), {"rolls_left": 2, "locked": [False] * 5})()
    dealer = type("D", (), {})()
    with patch.object(yahtzee, "_show_dice"), patch.object(yahtzee, "_show_scorecard"), \
         patch.object(yahtzee.io, "echo"):
        yahtzee._prompt_action(player, dealer)
    assert calls[0]["keys"] == ["l", "q", "r", "s"]
    assert calls[0]["default"] == "r"


# ---- tictactoe: move prompt is in a loop, so the seam contract is checked directly ---------

def test_tictactoe_options_are_a_bare_letter_run_the_seam_reads_per_key():
    """The move prompt passes PROMPT_OPTIONS as a bare run. Hosted, the seam must turn it into
    one key per character (digits and Q/R), not one key for the whole string."""
    calls = _hosted(["q"])
    host.choose("your move", tt.PROMPT_OPTIONS, default=None, clearline=False)
    assert calls[0]["keys"] == sorted(set(tt.PROMPT_OPTIONS))
    assert calls[0]["default"] is None


def test_tictactoe_clearline_is_dropped_when_hosted_and_kept_standalone():
    calls = _hosted(["q"])
    host.choose("your move", tt.PROMPT_OPTIONS, default=None, clearline=False)
    assert len(calls) == 1  # hosted call did not raise on the unknown keyword

    host.unregister_menu()
    with patch.object(host.io, "inputchoice", return_value="Q") as ic:
        host.choose("your move", tt.PROMPT_OPTIONS, default=None, clearline=False)
    assert ic.call_args.kwargs.get("clearline") is False


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
