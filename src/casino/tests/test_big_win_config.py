"""casino.config.get_big_win_settings: bed.json casino.slots.big_win, with safe defaults."""

from types import SimpleNamespace as NS

import pytest

from casino.config import BIG_WIN_DEFAULTS, get_big_win_settings


pytestmark = pytest.mark.unit


def _args(block):
    if block is None:
        return NS()
    return NS(_casino_config={"slots": {"big_win": block}})


def test_defaults_when_nothing_is_configured():
    assert get_big_win_settings(NS()) == BIG_WIN_DEFAULTS


def test_reads_both_keys():
    assert get_big_win_settings(_args({"enabled": False, "multiplier": 20})) == {"enabled": False, "multiplier": 20}


@pytest.mark.parametrize("bad", [0, -3, 2.5, "50", True])
def test_an_invalid_multiplier_falls_back_to_the_default(bad):
    assert get_big_win_settings(_args({"multiplier": bad}))["multiplier"] == BIG_WIN_DEFAULTS["multiplier"]


def test_a_non_boolean_enabled_falls_back_to_the_default():
    assert get_big_win_settings(_args({"enabled": "no"}))["enabled"] is BIG_WIN_DEFAULTS["enabled"]


def test_a_malformed_block_falls_back_to_the_defaults():
    assert get_big_win_settings(_args("oops")) == BIG_WIN_DEFAULTS
