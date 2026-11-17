"""The viewer watches the player's own blackjack table when no --table is given, not a placeholder table name."""

from casino.tk import viewer_login  # noqa: F401  (ensures the viewer package imports)

import importlib.util
import pathlib

import pytest


pytestmark = pytest.mark.unit

LAUNCHER = pathlib.Path(__file__).resolve().parents[3] / "scripts" / "round-view.py"


def _launcher():
    spec = importlib.util.spec_from_file_location("round_view_launcher", LAUNCHER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_default_table_follows_the_moniker():
    mod = _launcher()
    assert mod.default_table("jam") == "blackjack-jam"


def test_the_default_table_is_empty_when_there_is_no_moniker_yet():
    mod = _launcher()
    assert mod.default_table("") == ""
