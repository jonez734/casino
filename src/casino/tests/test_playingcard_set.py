"""casino reads its card set from casino.playingcard.set_name, defaulting to bicycle."""

from types import SimpleNamespace

import pytest

from casino import config

pytestmark = pytest.mark.unit


def _args(block):
    return SimpleNamespace(_casino_config={"playingcard": block} if block is not None else {})


def test_default_is_bicycle_when_nothing_is_configured():
    assert config.get_playingcard_set(SimpleNamespace()) == "bicycle"


def test_configured_set_is_returned():
    assert config.get_playingcard_set(_args({"set_name": "tarot"})) == "tarot"


@pytest.mark.parametrize("bad", [{}, {"set_name": ""}, {"set_name": "   "}, {"set_name": 7}])
def test_missing_or_invalid_set_name_falls_back_to_bicycle(bad):
    assert config.get_playingcard_set(_args(bad)) == "bicycle"


def test_non_dict_block_falls_back_to_bicycle():
    assert config.get_playingcard_set(SimpleNamespace(_casino_config={"playingcard": "x"})) == "bicycle"
