"""casino's game and tictactoe entry points use member.getcurrentmoniker, not the removed getcurrentid."""

from pathlib import Path

import pytest

CASINO = Path(__file__).resolve().parents[1]
FILES = [
    "tictactoe/__main__.py",
    "blackjack/game.py",
    "slots/game.py",
    "yahtzee/game.py",
]


@pytest.mark.parametrize("rel", FILES)
def test_file_does_not_call_getcurrentid(rel):
    src = (CASINO / rel).read_text()
    assert "getcurrentid(" not in src, rel


@pytest.mark.parametrize("rel", FILES)
def test_file_uses_getcurrentmoniker(rel):
    src = (CASINO / rel).read_text()
    assert "getcurrentmoniker(" in src, rel
