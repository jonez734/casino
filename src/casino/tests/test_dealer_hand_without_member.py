#!/usr/bin/env python3
# casino/tests/test_dealer_hand_without_member.py
# The dealer's hand must not need an engine.__member row. casino.__hand.playermoniker is a foreign key
# to engine.__member, so a dealer stored as "__dealer__" needed a fake member on every database. The
# dealer hand is now stored with no player and found by attrs.is_dealer. Stubbed: no database.

import inspect
from pathlib import Path

import pytest

from casino.dal import game as dal_game


@pytest.mark.unit
def test_dealer_hand_is_stored_without_a_player_moniker():
    src = inspect.getsource(dal_game.create_dealer_hand)
    assert "__dealer__" not in src
    assert "DEALER_MONIKER" not in src
    assert "playermoniker" in src and "NULL" in src


@pytest.mark.unit
def test_dealer_lookups_select_by_the_dealer_flag_not_the_moniker():
    src = Path(dal_game.__file__).read_text()
    assert "DEALER_MONIKER" not in src.replace("DEALER_MONIKER = ", "")
    assert "attrs->>'is_dealer'" in src or "is_dealer" in src
