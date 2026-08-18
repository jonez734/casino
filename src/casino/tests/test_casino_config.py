#!/usr/bin/env python3
# casino/tests/test_casino_config.py
# Unit tests for the casino config helpers
# (casino.config.get_casino_config, get_surrender_multiplier).

import argparse
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, "/home/opencode/data/work/casino/src")


def _make_args(**overrides) -> argparse.Namespace:
    args = argparse.Namespace()
    for k, v in overrides.items():
        setattr(args, k, v)
    return args


class TestGetCasinoConfig(unittest.TestCase):
    """``get_casino_config(args)`` prefers the wired namespace attr."""

    def test_returns_wired_when_set(self):
        from casino.config import get_casino_config

        cfg = {"blackjack": {"surrender_multiplier": 0.42}}
        args = _make_args(_casino_config=cfg, _casino_config_file="/nonexistent.json")
        self.assertEqual(get_casino_config(args), cfg)

    def test_falls_back_to_config_file_when_wiring_missing(self):
        from casino.config import get_casino_config

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"casino": {"blackjack": {"surrender_multiplier": 0.3}}}, f)
            path = f.name
        try:
            args = _make_args(_casino_config=None, _casino_config_file=path)
            self.assertEqual(
                get_casino_config(args),
                {"blackjack": {"surrender_multiplier": 0.3}},
            )
        finally:
            os.unlink(path)

    def test_returns_empty_when_neither_set(self):
        from casino.config import get_casino_config

        args = _make_args(_casino_config=None)
        self.assertEqual(get_casino_config(args), {})

    def test_returns_empty_when_file_missing(self):
        from casino.config import get_casino_config

        args = _make_args(
            _casino_config=None, _casino_config_file="/nonexistent.json"
        )
        self.assertEqual(get_casino_config(args), {})


class TestGetSurrenderMultiplier(unittest.TestCase):
    """``get_surrender_multiplier(args)`` reads from bed.json with a 0.5
    default and honors ``surrender_allowed``."""

    def test_default_when_no_config(self):
        from casino.config import get_surrender_multiplier

        args = _make_args()
        self.assertEqual(get_surrender_multiplier(args), 0.5)

    def test_honors_wired_config(self):
        from casino.config import get_surrender_multiplier

        args = _make_args(
            _casino_config={"blackjack": {"surrender_multiplier": 0.7}}
        )
        self.assertEqual(get_surrender_multiplier(args), 0.7)

    def test_disallowed_returns_zero(self):
        from casino.config import get_surrender_multiplier

        args = _make_args(
            _casino_config={
                "blackjack": {"surrender_allowed": False, "surrender_multiplier": 0.5}
            }
        )
        self.assertEqual(get_surrender_multiplier(args), 0.0)

    def test_disallowed_via_string_none(self):
        from casino.config import get_surrender_multiplier

        args = _make_args(
            _casino_config={
                "blackjack": {"surrender_allowed": "none", "surrender_multiplier": 0.5}
            }
        )
        self.assertEqual(get_surrender_multiplier(args), 0.0)

    def test_clamps_out_of_range_to_default(self):
        from casino.config import get_surrender_multiplier

        args = _make_args(
            _casino_config={"blackjack": {"surrender_multiplier": 1.5}}
        )
        self.assertEqual(get_surrender_multiplier(args), 0.5)

    def test_negative_multiplier_clamps_to_default(self):
        from casino.config import get_surrender_multiplier

        args = _make_args(
            _casino_config={"blackjack": {"surrender_multiplier": -0.1}}
        )
        self.assertEqual(get_surrender_multiplier(args), 0.5)

    def test_garbage_value_falls_back_to_default(self):
        from casino.config import get_surrender_multiplier

        args = _make_args(
            _casino_config={"blackjack": {"surrender_multiplier": "half"}}
        )
        self.assertEqual(get_surrender_multiplier(args), 0.5)


if __name__ == "__main__":
    unittest.main()
