#!/usr/bin/env python3
# casino/tests/test_slots_unit.py
# Unit tests for the slots lib + dealer modules.

import io as stdio
import random
import sys
import unittest

sys.path.insert(0, "/home/opencode/data/work/casino/src")

from bbsengine6.io import common

from casino.slots import lib
from casino.slots.dealer import SlotDealer


class TestSymbol(unittest.TestCase):
    def test_weight_must_be_positive(self):
        with self.assertRaises(ValueError):
            lib.Symbol("X", weight=0, glyph="x")
        with self.assertRaises(ValueError):
            lib.Symbol("X", weight=-1, glyph="x")

    def test_frozen(self):
        s = lib.Symbol("CHERRY", weight=8, glyph="c")
        with self.assertRaises(Exception):
            s.weight = 9  # type: ignore[misc]


class TestReel(unittest.TestCase):
    def test_unknown_symbol_raises(self):
        rng = lib.RNG(random.Random(0))
        with self.assertRaises(ValueError):
            lib.Reel(["CHERRY", "BOGUS"], lib.DEFAULT_SYMBOLS, rng)

    def test_spin_returns_symbol_from_strip(self):
        rng = lib.RNG(random.Random(0))
        reel = lib.Reel(["CHERRY", "LEMON", "BLANK"], lib.DEFAULT_SYMBOLS, rng)
        for _ in range(100):
            s = reel.spin()
            self.assertIn(s.name, {"CHERRY", "LEMON", "BLANK"})

    def test_strip_distribution(self):
        """A reel with uniform strip probabilities yields close to expected counts."""
        rng = lib.RNG(random.Random(0))
        reel = lib.Reel(["CHERRY", "LEMON"], lib.DEFAULT_SYMBOLS, rng)
        n = 10000
        a_count = sum(1 for _ in range(n) if reel.spin().name == "CHERRY")
        # 50/50 split; tolerance ±5%
        self.assertGreater(a_count / n, 0.45)
        self.assertLess(a_count / n, 0.55)


class TestPaytable(unittest.TestCase):
    def test_empty_paytable_pays_nothing(self):
        pt = lib.Paytable({})
        wins = pt.evaluate(
            [lib.Symbol("SEVEN", 1, "7")] * 5, bet=10
        )
        self.assertEqual(wins, [])

    def test_three_of_a_kind(self):
        pt = lib.Paytable({("SEVEN", "SEVEN", "SEVEN"): 50})
        wins = pt.evaluate(
            [lib.Symbol("SEVEN", 1, "7")] * 5, bet=10
        )
        self.assertEqual(len(wins), 1)
        self.assertEqual(wins[0].multiplier, 50)
        self.assertEqual(wins[0].payout, 500)

    def test_two_of_a_kind(self):
        pt = lib.Paytable({("SEVEN", "SEVEN"): 3})
        wins = pt.evaluate(
            [
                lib.Symbol("SEVEN", 1, "7"),
                lib.Symbol("SEVEN", 1, "7"),
                lib.Symbol("LEMON", 1, "l"),
                lib.Symbol("BAR", 1, "b"),
                lib.Symbol("BLANK", 1, "."),
            ],
            bet=10,
        )
        self.assertEqual(len(wins), 1)
        self.assertEqual(wins[0].payout, 30)

    def test_one_of_a_kind(self):
        pt = lib.Paytable({("CHERRY",): 1})
        wins = pt.evaluate(
            [lib.Symbol("CHERRY", 1, "c")] + [lib.Symbol("BLANK", 1, ".")] * 4,
            bet=10,
        )
        self.assertEqual(len(wins), 1)
        self.assertEqual(wins[0].payout, 10)

    def test_no_match(self):
        pt = lib.Paytable({("SEVEN", "SEVEN", "SEVEN"): 50})
        wins = pt.evaluate(
            [lib.Symbol("CHERRY", 1, "c")] * 5, bet=10
        )
        self.assertEqual(wins, [])

    def test_partial_match_does_not_pay_3oak(self):
        """Two SEVENs at the start do not pay the 3-of-a-kind."""
        pt = lib.Paytable({("SEVEN", "SEVEN", "SEVEN"): 50})
        wins = pt.evaluate(
            [
                lib.Symbol("SEVEN", 1, "7"),
                lib.Symbol("SEVEN", 1, "7"),
                lib.Symbol("LEMON", 1, "l"),
                lib.Symbol("BAR", 1, "b"),
                lib.Symbol("BLANK", 1, "."),
            ],
            bet=10,
        )
        self.assertEqual(wins, [])

    def test_rejects_non_tuple_key(self):
        with self.assertRaises(ValueError):
            lib.Paytable({"SEVEN": 5})  # type: ignore[dict-item]

    def test_rejects_negative_multiplier(self):
        with self.assertRaises(ValueError):
            lib.Paytable({("SEVEN",): -1})

    def test_zero_multiplier_skipped(self):
        pt = lib.Paytable({("SEVEN", "SEVEN", "SEVEN"): 0})
        wins = pt.evaluate(
            [lib.Symbol("SEVEN", 1, "7")] * 5, bet=10
        )
        self.assertEqual(wins, [])


class TestRNG(unittest.TestCase):
    def test_seeded_is_deterministic(self):
        r1 = lib.RNG(random.Random(123))
        r2 = lib.RNG(random.Random(123))
        items = [lib.Symbol("CHERRY", 1, "c"), lib.Symbol("LEMON", 1, "l")]
        s1 = [r1.choice_seq(items) for _ in range(20)]
        s2 = [r2.choice_seq(items) for _ in range(20)]
        self.assertEqual([s.name for s in s1], [s.name for s in s2])

    def test_weighted_distribution(self):
        rng = lib.RNG(random.Random(7))
        items = [
            lib.Symbol("CHERRY", 1, "c"),
            lib.Symbol("LEMON", 3, "l"),
        ]
        n = 20000
        a_count = sum(1 for _ in range(n) if rng.weighted_choice(items).name == "CHERRY")
        # Expected: 1/(1+3) = 25%
        self.assertGreater(a_count / n, 0.23)
        self.assertLess(a_count / n, 0.27)


class TestSlotDealer(unittest.TestCase):
    def test_rejects_no_reels(self):
        with self.assertRaises(ValueError):
            SlotDealer([], lib.Paytable())

    def test_play_rejects_non_positive_bet(self):
        rng = lib.RNG(random.Random(0))
        dealer = SlotDealer(lib.default_reels(lib.DEFAULT_SYMBOLS, rng), lib.Paytable(), rng)
        with self.assertRaises(ValueError):
            dealer.play(bet=0)
        with self.assertRaises(ValueError):
            dealer.play(bet=-5)

    def test_spin_grid_shape(self):
        rng = lib.RNG(random.Random(0))
        dealer = SlotDealer(lib.default_reels(lib.DEFAULT_SYMBOLS, rng), lib.Paytable(), rng)
        grid = dealer.spin_grid()
        self.assertEqual(len(grid), 5)
        for col in grid:
            self.assertEqual(len(col), 3)

    def test_center_row(self):
        grid = [
            [lib.Symbol("A", 1, "a"), lib.Symbol("B", 1, "b"), lib.Symbol("C", 1, "c")],
            [lib.Symbol("D", 1, "d"), lib.Symbol("E", 1, "e"), lib.Symbol("F", 1, "f")],
        ]
        center = SlotDealer.center_row(grid)
        self.assertEqual([s.name for s in center], ["B", "E"])

    def test_center_row_odd(self):
        grid = [
            [lib.Symbol("A", 1, "a"), lib.Symbol("B", 1, "b"), lib.Symbol("C", 1, "c"),
             lib.Symbol("D", 1, "d"), lib.Symbol("E", 1, "e")],
        ]
        center = SlotDealer.center_row(grid)
        self.assertEqual([s.name for s in center], ["C"])

    def test_play_deterministic_with_seed(self):
        rng1 = lib.RNG(random.Random(42))
        d1 = SlotDealer(lib.default_reels(lib.DEFAULT_SYMBOLS, rng1), lib.Paytable(), rng1)
        r1 = d1.play(bet=10)
        rng2 = lib.RNG(random.Random(42))
        d2 = SlotDealer(lib.default_reels(lib.DEFAULT_SYMBOLS, rng2), lib.Paytable(), rng2)
        r2 = d2.play(bet=10)
        self.assertEqual(r1.payout, r2.payout)
        self.assertEqual(r1.net, r2.net)
        self.assertEqual([s.name for s in r1.center_row], [s.name for s in r2.center_row])


class TestRTP(unittest.TestCase):
    """Asserts the realized RTP of the default paytable + reel strips
    is within +/- 0.05 of the 0.92 target over 50k spins. The theoretical
    RTP test below is the tight bound; the empirical test has more
    tolerance for sample noise.
    """

    TARGET = 0.92
    EMPIRICAL_TOLERANCE = 0.05
    n = 50_000

    def test_empirical_rtp_in_band(self):
        rng = lib.RNG(random.Random(20240101))
        dealer = SlotDealer(
            lib.default_reels(lib.DEFAULT_SYMBOLS, rng), lib.Paytable(), rng
        )
        total = 0
        for _ in range(self.n):
            r = dealer.play(bet=1)
            total += r.payout
        rtp = total / self.n
        self.assertGreater(
            rtp,
            self.TARGET - self.EMPIRICAL_TOLERANCE,
            f"RTP {rtp:.4f} below floor {self.TARGET - self.EMPIRICAL_TOLERANCE:.4f}",
        )
        self.assertLess(
            rtp,
            self.TARGET + self.EMPIRICAL_TOLERANCE,
            f"RTP {rtp:.4f} above ceiling {self.TARGET + self.EMPIRICAL_TOLERANCE:.4f}",
        )

    def test_theoretical_rtp_in_band(self):
        """Theoretical RTP is the source of truth. Assert it's within
        the design window [0.80, 0.99] (the same bounds enforced on
        per-table target_rtp config values).
        """
        rng = lib.RNG(random.Random(0))
        reels = lib.default_reels(lib.DEFAULT_SYMBOLS, rng)
        rtp = lib.Paytable().theoretical_rtp(reels)
        self.assertGreaterEqual(rtp, 0.80)
        self.assertLessEqual(rtp, 0.99)
        # And reasonably close to the 0.92 target
        self.assertLess(abs(rtp - self.TARGET), 0.05)

    def test_theoretical_rtp_with_progress_callback(self):
        """When progress_every > 0, the screen updateprogress helper is
        called at least once and the returned RTP matches the no-progress
        result exactly (fast-path is identical regardless of progress).
        """
        from unittest.mock import patch

        rng = lib.RNG(random.Random(0))
        reels = lib.default_reels(lib.DEFAULT_SYMBOLS, rng)

        rtp_no_progress = lib.Paytable().theoretical_rtp(reels)

        with patch("bbsengine6.io.screen.updateprogress") as mock_progress:
            rtp_with_progress = lib.Paytable().theoretical_rtp(
                reels, progress_every=1
            )

        self.assertAlmostEqual(rtp_with_progress, rtp_no_progress, places=10)
        self.assertGreater(
            mock_progress.call_count, 0, "updateprogress was never called"
        )

    def test_theoretical_rtp_silent_when_progress_zero(self):
        """Default progress_every=0 must not touch the screen module.
        Regression guard for the no-progress path.
        """
        from unittest.mock import patch

        rng = lib.RNG(random.Random(0))
        reels = lib.default_reels(lib.DEFAULT_SYMBOLS, rng)

        with patch("bbsengine6.io.screen.updateprogress") as mock_progress:
            rtp = lib.Paytable().theoretical_rtp(reels)
        self.assertGreater(rtp, 0.5)
        self.assertEqual(mock_progress.call_count, 0)

    def test_theoretical_rtp_screen_import_failure_is_safe(self):
        """If bbsengine6.io.screen can't be imported, RTP still returns
        a valid number (the lazy import must not raise).
        """
        from unittest.mock import patch

        rng = lib.RNG(random.Random(0))
        reels = lib.default_reels(lib.DEFAULT_SYMBOLS, rng)

        with patch.dict("sys.modules", {"bbsengine6.io.screen": None}):
            # Even with progress_every > 0, missing screen is non-fatal
            rtp = lib.Paytable().theoretical_rtp(reels, progress_every=1000)
        self.assertGreater(rtp, 0.5)


class TestRenderAscii(unittest.TestCase):
    def test_renders_with_correct_symbols(self):
        # Glyph is the first character of the symbol name (for the test
        # we don't want to depend on emoji rendering).
        grid = [[lib.Symbol(s, 1, s[0]) for s in col] for col in [
            ["CHERRY", "CHERRY", "CHERRY"],
            ["LEMON", "LEMON", "LEMON"],
            ["PLUM", "PLUM", "PLUM"],
            ["BELL", "BELL", "BELL"],
            ["BAR", "BAR", "BAR"],
        ]]
        result = lib.SpinResult(
            reels=grid,
            center_row=[col[1] for col in grid],
            wins=[],
            bet=1,
            payout=0,
            net=-1,
        )
        out = lib.render_ascii(result)
        # First letter of each symbol is the glyph
        self.assertIn("C", out)
        self.assertIn("L", out)
        self.assertIn("B", out)
        # Center row is highlighted with {inverse} ... {/inverse}
        self.assertIn("{inverse}", out)
        self.assertIn("{/inverse}", out)
        # box characters
        self.assertIn("┌", out)
        self.assertIn("└", out)

    def test_renders_with_color_wrappers(self):
        """When a symbol has a color, its cell wraps the glyph in
        {color}...{/color} so bbsengine6.io.echo can resolve it.
        """
        result = lib.SpinResult(
            reels=[[lib.Symbol("CHERRY", 1, "C", "red")]],
            center_row=[lib.Symbol("CHERRY", 1, "C", "red")],
            wins=[],
            bet=1,
            payout=0,
            net=-1,
        )
        out = lib.render_ascii(result)
        self.assertIn("{red}", out)
        self.assertIn("{/red}", out)

    def test_renders_without_color_when_symbol_has_none(self):
        """Empty color string means no color wrappers are emitted."""
        result = lib.SpinResult(
            reels=[[lib.Symbol("BLANK", 1, ".", "")]],
            center_row=[lib.Symbol("BLANK", 1, ".", "")],
            wins=[],
            bet=1,
            payout=0,
            net=-1,
        )
        out = lib.render_ascii(result)
        self.assertNotIn("{", out)
        self.assertNotIn("}", out)

    def test_renders_empty(self):
        result = lib.SpinResult(
            reels=[],
            center_row=[],
            wins=[],
            bet=1,
            payout=0,
            net=-1,
        )
        self.assertEqual(lib.render_ascii(result), "")

    def test_render_ascii_echoes_without_crash(self):
        """Pipe render_ascii() output through bbsengine6.io.echo_iter()
        to verify closing palette color tags (e.g. {/red}) no longer
        crash echo and produce the proper default-fg reset."""
        import importlib
        em = importlib.import_module("bbsengine6.io.echo")

        syms = [
            lib.Symbol("CHERRY", 1, "C", "red"),
            lib.Symbol("LEMON", 1, "L", "yellow"),
            lib.Symbol("BLANK", 1, ".", ""),
        ]
        reels = [
            [syms[0], syms[1], syms[2]],
            [syms[1], syms[0], syms[2]],
            [syms[2], syms[0], syms[1]],
            [syms[0], syms[2], syms[1]],
            [syms[1], syms[2], syms[0]],
        ]
        center = [col[1] for col in reels]
        result = lib.SpinResult(
            reels=reels,
            center_row=center,
            wins=[],
            bet=10,
            payout=0,
            net=-10,
        )
        out = lib.render_ascii(result)

        tokens = []
        try:
            for tok in em.echo_iter(out, wordwrap=False):
                tokens.append(tok)
        except Exception as e:
            self.fail(f"echo_iter raised {type(e).__name__}: {e}")

        # For each fg-colored cell, we expect an open sequence
        # (\x1b[38;2;...m) followed by the glyph, then a default-fg
        # reset (\x1b[39m).
        fg_open = "\x1b[38;2;136;0;0m"   # cherry red
        fg_open_l = "\x1b[38;2;238;238;119m"  # lemon yellow
        default_fg = "\x1b[39m"
        joined = "".join(t.text or "" for t in tokens if t.text)
        self.assertIn(fg_open, joined)
        self.assertIn(fg_open_l, joined)
        self.assertIn(default_fg, joined)

        # Center row is inverse-highlighted; expect at least one
        # inverse open (\x1b[7m) and inverse close (\x1b[27m).
        self.assertIn("\x1b[7m", joined)
        self.assertIn("\x1b[27m", joined)


class TestSpinResultDataclass(unittest.TestCase):
    def test_to_dict(self):
        r = lib.SpinResult(
            reels=[[lib.Symbol("X", 1, "x")]],
            center_row=[lib.Symbol("X", 1, "x")],
            wins=[lib.Win(("X",), 2, 4)],
            bet=2,
            payout=4,
            net=2,
        )
        d = r.to_dict()
        self.assertEqual(d["bet"], 2)
        self.assertEqual(d["payout"], 4)
        self.assertEqual(d["net"], 2)
        self.assertEqual(d["reels"], [["X"]])
        self.assertEqual(d["center_row"], ["X"])
        self.assertEqual(d["wins"][0]["multiplier"], 2)

    def test_did_win(self):
        win = lib.SpinResult([], [], [lib.Win(("X",), 1, 1)], 1, 1, 0)
        loss = lib.SpinResult([], [], [], 1, 0, -1)
        self.assertTrue(win.did_win)
        self.assertFalse(loss.did_win)


class TestDefaults(unittest.TestCase):
    def test_default_symbols_have_positive_weight(self):
        for name, sym in lib.DEFAULT_SYMBOLS.items():
            self.assertGreater(sym.weight, 0, f"{name} weight should be > 0")

    def test_default_reels_known_symbols(self):
        for i, reel in enumerate(lib.DEFAULT_REELS):
            for stop in reel:
                self.assertIn(stop, lib.DEFAULT_SYMBOLS, f"reel {i} has unknown stop {stop}")

    def test_default_paytable_keys_known_symbols(self):
        for key in lib.DEFAULT_PAYTABLE:
            for s in key:
                self.assertIn(s, lib.DEFAULT_SYMBOLS, f"paytable key references unknown symbol {s}")


class TestEchoMarkup(unittest.TestCase):
    """Verify that bbsengine6.io.echo markup used by slots is
    interpreted as color escapes, not printed as literal text.

    Regression guard: a previous bug in casino_client.py passed a
    plain ``"{{var:...}}..."`` string to ``io.echo``, which rendered
    the doubled braces verbatim instead of expanding the color
    variable. These tests confirm the slots module never falls into
    that pattern, and that its f-string ``{{var:...}}`` literals
    escape cleanly through the bbsengine6 echo pipeline.
    """

    def setUp(self):
        self._buf = stdio.StringIO()
        self._old_stream = common._current_output_stream
        common.set_output_stream(self._buf)

    def tearDown(self):
        common.set_output_stream(self._old_stream)

    def _captured(self) -> str:
        return self._buf.getvalue()

    def test_smoke_spin_emits_color_escapes(self):
        """``_smoke_spin`` uses f-string ``{{var:labelcolor}}...``
        literals; Python's f-string escaping reduces them to
        ``{var:labelcolor}`` and ``io.echo`` must expand them into
        ANSI CSI sequences.
        """
        from casino.slots.__main__ import _smoke_spin

        _smoke_spin(seed=42, rtp_progress=0)
        out = self._captured()

        self.assertIn("\x1b[", out, "expected ANSI escapes in smoke-spin output")
        self.assertNotIn("{{", out, "doubled braces leaked through echo (literal text)")
        self.assertNotIn(
            "var:labelcolor", out, "{var:labelcolor} not interpreted by io.echo"
        )
        self.assertNotIn(
            "var:valuecolor", out, "{var:valuecolor} not interpreted by io.echo"
        )
        self.assertIn("total reels:", out)
        self.assertIn("target RTP:", out)

    def test_render_bet_help_emits_color_escapes(self):
        """``play._render_bet_help`` echoes plain ``{var:optioncolor}``
        strings; ``io.echo`` must interpret them into ANSI escapes
        and never print the markup literally.
        """
        from casino.slots.play import _render_bet_help

        _render_bet_help()
        out = self._captured()

        self.assertIn("\x1b[", out, "expected ANSI escapes in bet-help output")
        self.assertNotIn("{{", out, "doubled braces leaked through echo")
        self.assertNotIn(
            "var:optioncolor", out, "{var:optioncolor} not interpreted by io.echo"
        )
        self.assertNotIn(
            "var:labelcolor", out, "{var:labelcolor} not interpreted by io.echo"
        )

    def test_double_braces_in_fstring_round_trip(self):
        """A literal ``{{var:foo}}`` written as ``f"{{{{var:foo}}}}"``
        is a programmer mistake: the f-string collapses to the
        double-brace plain string, which ``io.echo`` does NOT
        interpret. This test pins that behavior so callers don't
        regress to the broken pattern.
        """
        from bbsengine6 import io

        io.echo(f"{{{{var:promptcolor}}}}hello{{{{var:inputcolor}}}}")
        out = self._captured()

        self.assertIn("{{var:promptcolor}}", out)
        self.assertIn("{{var:inputcolor}}", out)
        self.assertNotIn("\x1b[38;", out)

    def test_plain_string_single_brace_is_interpreted(self):
        """The slots ``play`` module passes plain strings with
        single-brace ``{var:optioncolor}`` markup to ``io.echo``;
        that markup must expand to ANSI escapes.
        """
        from bbsengine6 import io

        io.echo("{var:optioncolor}[B]{var:labelcolor}et")
        out = self._captured()

        self.assertIn("\x1b[", out)
        self.assertNotIn("var:optioncolor", out)
        self.assertNotIn("var:labelcolor", out)


if __name__ == "__main__":
    unittest.main()
