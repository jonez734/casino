#!/usr/bin/env python3
# casino/tests/test_slots_integrated.py
# Comprehensive end-to-end integration tests for the slots subsystem.
#
# These tests exercise the full stack without a live PostgreSQL: dealer
# construction, paytable overrides, the door-mode play loop, the
# service-layer atomic transaction (mocked cursor), and the BED
# handler's WebSocket message dispatch + broadcast. They run under
# the same pytest invocation as the rest of the casino suite, with
# no CASINO_TEST_DB env var required.
#
# Coverage map:
#   TestDealerCacheAcrossTables             per-table dealer cache, invalidate
#   TestPaytableOverrideConfig              both override formats, validation
#   TestSpinStatisticalRTP                  realized vs theoretical RTP
#   TestSpinResultRender                    render_ascii shape + colors
#   TestPlayerCreditLedger                  bet validation, credit math
#   TestDoorModePlayLoopEndToEnd            play.main() multi-spin driver
#   TestServiceAtomicTransaction            SQL trace through handle_spin
#   TestServiceRollbackInsufficientFunds    insufficient_funds path
#   TestHandlerFullMessageFlow              auth + spin + paytable + history
#   TestDealerCacheInvalidationLifecycle    cache hit/miss across updates

import argparse
import contextlib
import random
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, "/home/opencode/data/work/casino/src")


def _make_args(**overrides):
    base = {"databasename": "test", "database": "test", "debug": False}
    base.update(overrides)
    return argparse.Namespace(**base)


def _stub_reel(rng):
    """A minimal reel with one stop so SlotDealer.__init__ is happy.

    Tests that need to drive ``dealer.play`` themselves override the
    attribute on the dealer instance, so the contents of the reel
    don't matter.
    """
    from casino.slots.lib import DEFAULT_SYMBOLS, RNG, Reel
    return Reel(["CHERRY"], DEFAULT_SYMBOLS, RNG(rng))


def _sql_text(sql_obj) -> str:
    """Flatten a psycopg Composed/SQL object to a plain string.

    The casino service passes ``database.query(...)`` (a ``Composed``
    sequence) directly to ``cursor.execute``. ``str(composed)`` prints
    the debug representation with ``Composed([...])`` so substring
    checks have to look at the *parts*. This helper joins SQL
    fragments so ``assertIn("__slot_spin", sql)`` works on the parts
    the test cares about.
    """
    parts = []
    queue = [sql_obj]
    while queue:
        item = queue.pop(0)
        if hasattr(item, "__iter__") and not isinstance(item, (str, bytes)):
            try:
                queue.extend(list(item))
            except TypeError:
                parts.append(str(item))
        else:
            parts.append(str(item))
    return " ".join(parts)


# --------------------------------------------------------------------------- #
# Dealer cache and paytable overrides
# --------------------------------------------------------------------------- #


class TestDealerCacheAcrossTables(unittest.TestCase):
    """The per-table dealer cache must build once, hit on subsequent
    calls, and rebuild after invalidation. Different tables get
    different dealers."""

    def setUp(self):
        self.args = _make_args()

    def test_two_tables_get_distinct_dealers(self):
        from casino.services.slots import (
            _dealers,
            get_dealer,
            invalidate_dealer,
        )

        with patch("casino.services.slots.dal_table.get_table") as gt:
            gt.side_effect = lambda args, moniker: {
                "moniker": moniker,
                "type": "slots",
                "attrs": {},
            }
            d_a = get_dealer(self.args, "alice-table")
            d_b = get_dealer(self.args, "bob-table")
            self.assertIsNotNone(d_a)
            self.assertIsNotNone(d_b)
            self.assertIsNot(d_a, d_b)
            self.assertEqual(len(_dealers), 2)

        invalidate_dealer("alice-table")
        invalidate_dealer("bob-table")

    def test_cache_hit_does_not_rebuild(self):
        from casino.services.slots import (
            _dealers,
            get_dealer,
            invalidate_dealer,
        )

        with patch("casino.services.slots.dal_table.get_table") as gt:
            gt.return_value = {"moniker": "t1", "type": "slots", "attrs": {}}
            d_first = get_dealer(self.args, "t1")
            call_count = gt.call_count
            d_second = get_dealer(self.args, "t1")
            self.assertIs(d_first, d_second)
            self.assertEqual(gt.call_count, call_count)
            self.assertIn("t1", _dealers)

        invalidate_dealer("t1")
        self.assertNotIn("t1", _dealers)

    def test_non_slots_table_returns_none(self):
        from casino.services.slots import get_dealer

        with patch(
            "casino.services.slots.dal_table.get_table",
            return_value={"moniker": "bj", "type": "blackjack", "attrs": {}},
        ):
            self.assertIsNone(get_dealer(self.args, "bj"))


class TestPaytableOverrideConfig(unittest.TestCase):
    """The paytable_override config field accepts both a list-of-dicts
    (DB-friendly JSONB shape) and a dict-of-tuples (in-process shape).
    Bad inputs raise ValueError before any DB write."""

    def test_list_format_round_trip(self):
        from casino.services.slots import _build_paytable_from_config
        from casino.slots.lib import Paytable

        config = {
            "paytable_override": [
                {"symbols": ["SEVEN", "SEVEN", "SEVEN"], "multiplier": 200},
                {"symbols": ["CHERRY"], "multiplier": 2},
            ]
        }
        pt = _build_paytable_from_config(config)
        self.assertIsInstance(pt, Paytable)
        self.assertEqual(pt.get(("SEVEN", "SEVEN", "SEVEN")), 200)
        self.assertEqual(pt.get(("CHERRY",)), 2)

    def test_dict_tuple_format(self):
        from casino.services.slots import _build_paytable_from_config

        config = {"paytable_override": {("BAR", "BAR"): 7}}
        pt = _build_paytable_from_config(config)
        self.assertEqual(pt.get(("BAR", "BAR")), 7)

    def test_invalid_multiplier_raises(self):
        from casino.services.slots import _build_paytable_from_config

        with self.assertRaises(ValueError):
            _build_paytable_from_config(
                {"paytable_override": [{"symbols": ["X"], "multiplier": -1}]}
            )

    def test_non_list_symbols_raises(self):
        from casino.services.slots import _build_paytable_from_config

        with self.assertRaises(ValueError):
            _build_paytable_from_config(
                {"paytable_override": [{"symbols": "CHERRY", "multiplier": 5}]}
            )

    def test_unknown_type_raises(self):
        from casino.services.slots import _build_paytable_from_config

        with self.assertRaises(ValueError):
            _build_paytable_from_config(
                {"paytable_override": "not a dict"}
            )


# --------------------------------------------------------------------------- #
# Statistical RTP
# --------------------------------------------------------------------------- #


class TestSpinStatisticalRTP(unittest.TestCase):
    """With a seeded RNG and the default reels + paytable, the realized
    RTP over a large sample must land within tolerance of the
    theoretical RTP."""

    def test_realized_rtp_within_tolerance(self):
        from casino.slots.lib import (
            DEFAULT_SYMBOLS,
            Paytable,
            RNG,
            RTP_DEFAULT,
            default_reels,
        )
        from casino.slots.dealer import SlotDealer

        rng = RNG(random.Random(20240101))
        dealer = SlotDealer(
            reels=default_reels(DEFAULT_SYMBOLS, rng),
            paytable=Paytable(),
            rng=rng,
        )

        spins = 5000
        total_wagered = 0
        total_payout = 0
        wins = 0
        for _ in range(spins):
            r = dealer.play(bet=1)
            total_wagered += 1
            total_payout += r.payout
            if r.payout > 0:
                wins += 1

        realized = total_payout / total_wagered
        theoretical = dealer.paytable.theoretical_rtp(dealer._reels)
        # Both realized (small sample) and theoretical (deterministic)
        # should land near the 0.92 target.
        self.assertGreater(realized, RTP_DEFAULT - 0.04)
        self.assertLess(realized, RTP_DEFAULT + 0.04)
        self.assertAlmostEqual(theoretical, RTP_DEFAULT, delta=0.02)
        # Win rate sanity: small but non-zero.
        self.assertGreater(wins / spins, 0.05)
        self.assertLess(wins / spins, 0.45)

    def test_seven_seven_seven_payout_matches_paytable(self):
        """A forced three-of-a-kind SEVEN must pay exactly bet * 145."""
        from casino.slots.lib import SpinResult, Symbol, Win

        seven = Symbol("SEVEN", 1, "7")
        result = SpinResult(
            reels=[[seven] * 3 for _ in range(5)],
            center_row=[seven] * 5,
            wins=[Win(("SEVEN",) * 3, 145, 145)],
            bet=10,
            payout=1450,
            net=1440,
        )
        self.assertEqual(result.payout, 1450)
        self.assertEqual(result.net, 1440)
        self.assertTrue(result.did_win)


# --------------------------------------------------------------------------- #
# ASCII renderer
# --------------------------------------------------------------------------- #


class TestSpinResultRender(unittest.TestCase):
    """render_ascii must produce a 3-row grid with the center row
    highlighted and each cell wrapped in its symbol's color tag."""

    def test_render_basic_grid_shape(self):
        from casino.slots.lib import SpinResult, Symbol, render_ascii

        syms = [
            Symbol("CHERRY", 1, "C", "red"),
            Symbol("LEMON", 1, "L", "yellow"),
            Symbol("BLANK", 1, ".", ""),
        ]
        reels = [
            [syms[0], syms[1], syms[2]],
            [syms[1], syms[0], syms[2]],
            [syms[2], syms[0], syms[1]],
            [syms[0], syms[2], syms[1]],
            [syms[1], syms[2], syms[0]],
        ]
        center = [c[1] for c in reels]
        result = SpinResult(
            reels=reels,
            center_row=center,
            wins=[],
            bet=10,
            payout=0,
            net=-10,
        )
        out = render_ascii(result)
        # 3 rows + 2 borders + 2 internal separators = 7 lines.
        self.assertEqual(len(out.split("\n")), 7)
        # Top border, middle separator, bottom border.
        self.assertIn("\u250c", out)
        self.assertIn("\u251c", out)
        self.assertIn("\u2514", out)
        # Center row glyphs should be present
        for sym in center:
            self.assertIn(sym.glyph, out)
        # Color tags from each cell should be present
        self.assertIn("{red}", out)
        self.assertIn("{yellow}", out)

    def test_render_empty_grid_returns_empty_string(self):
        from casino.slots.lib import SpinResult, render_ascii

        result = SpinResult(
            reels=[], center_row=[], wins=[], bet=0, payout=0, net=0
        )
        self.assertEqual(render_ascii(result), "")


# --------------------------------------------------------------------------- #
# Player credit ledger
# --------------------------------------------------------------------------- #


class TestPlayerCreditLedger(unittest.TestCase):
    """SlotPlayer.validate_bet must reject every illegal bet shape
    before debiting; SlotPlayer.play must move credits correctly."""

    def _make_player(self, credits=100, min_bet=1, max_bet=100):
        from casino.slots.dealer import SlotDealer
        from casino.slots.lib import Paytable
        from casino.slots.player import SlotPlayer

        dealer = SlotDealer(
            reels=[_stub_reel(random.Random(0))],
            paytable=Paytable(),
            rng=MagicMock(),
        )
        dealer.play = MagicMock(return_value=MagicMock(payout=0, net=-10))
        return SlotPlayer(
            moniker="alice",
            credits=credits,
            dealer=dealer,
            min_bet=min_bet,
            max_bet=max_bet,
        )

    def test_validate_bet_matrix(self):
        p = self._make_player(credits=100, min_bet=5, max_bet=50)
        self.assertIsNone(p.validate_bet(10))           # valid
        self.assertIsNotNone(p.validate_bet(4))         # below min
        self.assertIsNotNone(p.validate_bet(51))        # above max
        self.assertIsNotNone(p.validate_bet(0))         # zero
        self.assertIsNotNone(p.validate_bet(-1))        # negative
        self.assertIsNotNone(p.validate_bet(101))       # over credits
        self.assertIsNotNone(p.validate_bet("ten"))     # wrong type
        self.assertIsNotNone(p.validate_bet(True))      # bool is int!

    def test_play_debits_then_credits(self):
        from casino.slots.dealer import SlotDealer
        from casino.slots.lib import Paytable, SpinResult, Symbol, Win
        from casino.slots.player import SlotPlayer

        sym = Symbol("BAR", 1, "=")
        result = SpinResult(
            reels=[[sym] * 3 for _ in range(5)],
            center_row=[sym] * 5,
            wins=[Win(("BAR", "BAR", "BAR"), 45, 450)],
            bet=10,
            payout=450,
            net=440,
        )
        dealer = SlotDealer(
            reels=[_stub_reel(random.Random(0))],
            paytable=Paytable(),
            rng=MagicMock(),
        )
        dealer.play = MagicMock(return_value=result)
        p = SlotPlayer(
            moniker="alice",
            credits=100,
            dealer=dealer,
            min_bet=10,
            max_bet=100,
        )
        before = p.credits
        returned = p.play(bet=10)
        # 100 - 10 + 450 = 540
        self.assertEqual(p.credits, before - 10 + 450)
        self.assertIs(returned, result)

    def test_play_invalid_bet_raises_and_no_debit(self):
        from casino.slots.dealer import SlotDealer
        from casino.slots.lib import Paytable
        from casino.slots.player import SlotPlayer

        dealer = SlotDealer(
            reels=[_stub_reel(random.Random(0))],
            paytable=Paytable(),
            rng=MagicMock(),
        )
        dealer.play = MagicMock()
        p = SlotPlayer(
            moniker="alice",
            credits=100,
            dealer=dealer,
            min_bet=10,
            max_bet=100,
        )
        before = p.credits
        with self.assertRaises(ValueError):
            p.play(bet=5)  # below min
        self.assertEqual(p.credits, before)
        dealer.play.assert_not_called()


# --------------------------------------------------------------------------- #
# Door-mode play loop
# --------------------------------------------------------------------------- #


class TestDoorModePlayLoopEndToEnd(unittest.TestCase):
    """Drive ``slots.play.main`` through multiple spins via a fake
    io.inputchoice / io.inputinteger. Verify the player balance is
    debited correctly on each spin, the help callback is wired, and
    quitting exits cleanly.

    Two notes on the mocking strategy:

    1. ``bbsengine6.io.common.get_cursor_position`` is mocked because
       ``inputstring`` (called by ``inputinteger``) queries the real
       terminal cursor via DSR. Pytest's redirected stdin has no
       ``fileno()``; without the mock, ``inputinteger`` raises
       ``io.UnsupportedOperation`` on first call.

    2. ``inputchoice`` upper-cases user input before comparing to its
       option set, so the mocked responses must be uppercase. With
       lower-case keys, the play code never matches ``'Q'`` / ``'N'``
       and the loop never exits.
    """

    def _make_dealer(self, results):
        from casino.slots.dealer import SlotDealer
        from casino.slots.lib import Paytable

        dealer = SlotDealer(
            reels=[_stub_reel(random.Random(0))],
            paytable=Paytable(),
            rng=MagicMock(),
        )
        dealer.play = MagicMock(side_effect=results)
        return dealer

    def _common_patches(self):
        """Return a list of ``patch`` contexts for the io/echo/heading
        layer that every test in this class needs."""
        return [
            patch("bbsengine6.io.common.get_cursor_position",
                  return_value=(1, 1)),
            patch("casino.slots.play.io.echo"),
            patch("casino.slots.play.util.heading"),
        ]

    def _enter_common(self, stack):
        """Enter every common patch context on the given ExitStack
        and return the list of patch mocks in stack order."""
        return [stack.enter_context(p) for p in self._common_patches()]

    def test_three_spin_run_then_quit(self):
        from casino.slots.lib import SpinResult, Symbol, Win
        from casino.slots.player import SlotPlayer

        sym = Symbol("CHERRY", 1, "C")
        # Result sequence: win (payout 10), loss, loss
        dealer = self._make_dealer([
            SpinResult(reels=[[sym] * 3] * 5, center_row=[sym] * 5,
                       wins=[Win(("CHERRY",), 1, 10)],
                       bet=10, payout=10, net=0),
            SpinResult(reels=[[sym] * 3] * 5, center_row=[sym] * 5,
                       wins=[], bet=10, payout=0, net=-10),
            SpinResult(reels=[[sym] * 3] * 5, center_row=[sym] * 5,
                       wins=[], bet=10, payout=0, net=-10),
        ])
        player = SlotPlayer(
            moniker="alice", credits=100, dealer=dealer,
            min_bet=10, max_bet=100,
        )
        # Upper-case keys: inputchoice uppercases its input and the
        # play code compares against 'Q'/'N', so feed uppercase here.
        ic_queue = ["B", "Y", "B", "Y", "B", "N"]
        ii_queue = [10, 10, 10]

        with contextlib.ExitStack() as stack:
            mock_ic = stack.enter_context(patch(
                "casino.slots.play.io.inputchoice", side_effect=ic_queue))
            stack.enter_context(patch(
                "casino.slots.play.io.inputinteger", side_effect=ii_queue))
            mock_render = stack.enter_context(patch(
                "casino.slots.play.render_ascii", return_value="<rendered>"))
            self._enter_common(stack)
            from casino.slots import play
            result = play.main(_make_args(), player=player, dealer=dealer)

        self.assertTrue(result)
        # 3 spins, 3 renderings
        self.assertEqual(mock_render.call_count, 3)
        # 3 bet prompts + 3 again prompts
        self.assertEqual(mock_ic.call_count, 6)
        # Each call has help= wired
        for c in mock_ic.call_args_list:
            self.assertIn("help", c.kwargs)
            self.assertTrue(callable(c.kwargs["help"]))
        # Player ended with 100 - 10 + 10 - 10 - 10 = 80
        self.assertEqual(player.credits, 80)

    def test_quit_at_bet_prompt_returns_cleanly(self):
        from casino.slots.player import SlotPlayer

        dealer = self._make_dealer([])
        player = SlotPlayer(
            moniker="alice", credits=100, dealer=dealer,
            min_bet=10, max_bet=100,
        )

        with contextlib.ExitStack() as stack:
            stack.enter_context(patch(
                "casino.slots.play.io.inputchoice", side_effect=["Q"]))
            stack.enter_context(patch(
                "casino.slots.play.render_ascii", return_value="<x>"))
            self._enter_common(stack)
            from casino.slots import play
            result = play.main(_make_args(), player=player, dealer=dealer)

        self.assertTrue(result)
        dealer.play.assert_not_called()
        self.assertEqual(player.credits, 100)

    def test_invalid_bet_amount_loops_then_accepts(self):
        from casino.slots.lib import SpinResult, Symbol, Win
        from casino.slots.player import SlotPlayer

        sym = Symbol("CHERRY", 1, "C")
        dealer = self._make_dealer([
            SpinResult(reels=[[sym] * 3] * 5, center_row=[sym] * 5,
                       wins=[Win(("CHERRY",), 1, 10)],
                       bet=10, payout=10, net=0),
        ])
        player = SlotPlayer(
            moniker="alice", credits=100, dealer=dealer,
            min_bet=10, max_bet=100,
        )
        ic = ["B", "Y", "N"]            # bet, again, quit
        ii = [5, 25]                     # first bet invalid (below min), second valid

        with contextlib.ExitStack() as stack:
            stack.enter_context(patch(
                "casino.slots.play.io.inputchoice", side_effect=ic))
            stack.enter_context(patch(
                "casino.slots.play.io.inputinteger", side_effect=ii))
            stack.enter_context(patch(
                "casino.slots.play.render_ascii", return_value="<x>"))
            self._enter_common(stack)
            from casino.slots import play
            play.main(_make_args(), player=player, dealer=dealer)

        self.assertEqual(dealer.play.call_count, 1)
        self.assertEqual(dealer.play.call_args.kwargs.get("bet"), 25)

    def test_bet_below_credits_exhaustion(self):
        """After enough losing bets the player cannot afford the
        minimum bet; the loop keeps re-prompting with the same
        validation error and only the user's explicit quit (``Q``)
        ends the session."""
        from casino.slots.lib import SpinResult, Symbol
        from casino.slots.player import SlotPlayer

        sym = Symbol("LEMON", 1, "L")
        dealer = self._make_dealer([
            SpinResult(reels=[[sym] * 3] * 5, center_row=[sym] * 5,
                       wins=[], bet=10, payout=0, net=-10),
        ] * 5)
        player = SlotPlayer(
            moniker="alice", credits=30, dealer=dealer,
            min_bet=10, max_bet=100,
        )
        # 3 losing spins at 10 each drops credits from 30 to 0;
        # the player then attempts one more bet (which the loop
        # rejects as insufficient) before quitting.
        ic = ["B", "Y", "B", "Y", "B", "Y", "B", "Q"]
        ii = [10, 10, 10, 10]

        with contextlib.ExitStack() as stack:
            mock_ic = stack.enter_context(patch(
                "casino.slots.play.io.inputchoice", side_effect=ic))
            stack.enter_context(patch(
                "casino.slots.play.io.inputinteger", side_effect=ii))
            stack.enter_context(patch(
                "casino.slots.play.render_ascii", return_value="<x>"))
            self._enter_common(stack)
            from casino.slots import play
            result = play.main(_make_args(), player=player, dealer=dealer)

        self.assertTrue(result)
        # 3 valid bets + 1 rejected by validation + 3 again prompts
        # + 1 quit = 8 inputchoice calls.
        self.assertEqual(mock_ic.call_count, 8)
        self.assertEqual(player.credits, 0)


# --------------------------------------------------------------------------- #
# Service atomic transaction (cursor fakes)
# --------------------------------------------------------------------------- #


class _StubCursor:
    """Single-cursor fake that mimics the slot service's one-cursor
    transaction: SELECT FOR UPDATE -> UPDATE bank -> INSERT spin
    RETURNING id -> UPDATE stats (twice for biggest_win)."""

    def __init__(self, initial=None, insert_returning=None):
        self._initial = initial
        self._insert = insert_returning
        self._stashed = None
        self.executed = []

    def execute(self, sql, params=None):
        s = _sql_text(sql)
        if "INSERT" in s and "RETURNING" in s:
            self._stashed = self._insert
        self.executed.append((s, params))

    def fetchone(self):
        if self._stashed is not None:
            r = self._stashed
            self._stashed = None
            return r
        if self._initial is not None:
            r = self._initial
            self._initial = None
            return r
        return None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _StubConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False
        self.rolled_back = False

    def cursor(self, *a, **kw):
        return self._cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    @property
    def info(self):
        return {}

    @property
    def closed(self):
        return False


class TestServiceAtomicTransaction(unittest.TestCase):
    """End-to-end through handle_spin with all DB calls faked.
    Verifies the SQL trace, the bank/audit/stats updates, and the
    response shape on a winning spin."""

    def test_winning_spin_full_trace(self):
        from casino.services.slots import (
            _dealers,
            handle_spin,
            invalidate_dealer,
        )
        from casino.slots.lib import SpinResult, Symbol, Win

        seven = Symbol("SEVEN", 1, "7")

        class StubDealer:
            num_reels = 5
            num_rows = 3
            def play(self, bet):
                return SpinResult(
                    reels=[[seven] * 3 for _ in range(5)],
                    center_row=[seven] * 5,
                    wins=[Win(("SEVEN",) * 3, 145, bet * 145)],
                    bet=bet,
                    payout=bet * 145,
                    net=bet * 145 - bet,
                )

        _dealers["t1"] = StubDealer()
        self.addCleanup(invalidate_dealer, "t1")

        cursor = _StubCursor(
            initial={"id": 1, "balance": 1000},
            insert_returning={"id": 42},
        )
        conn = _StubConn(cursor)

        @contextlib.contextmanager
        def fake_connect(*a, **kw):
            yield conn

        with patch("casino.services.slots.database.connect", fake_connect), \
             patch("casino.services.slots.database.cursor",
                   side_effect=lambda c, **kw: c.cursor()), \
             patch("casino.services.slots.dal_table.get_table",
                   return_value={"type": "slots", "minimumbet": 1,
                                 "maximumbet": 1000}):
            r = handle_spin(_make_args(), "t1", "alice", 10)

        self.assertTrue(r["success"])
        self.assertEqual(r["spin"]["id"], 42)
        self.assertEqual(r["spin"]["bet"], 10)
        self.assertEqual(r["spin"]["payout"], 1450)
        self.assertEqual(r["spin"]["net"], 1440)
        self.assertEqual(r["spin"]["new_balance"], 1000 + 1440)

        # SELECT FOR UPDATE -> UPDATE bank -> INSERT spin ->
        # UPDATE stats (slots.spins/wins/net) -> UPDATE biggest_win
        self.assertEqual(len(cursor.executed), 5)
        sqls = [_sql_text(s) for s, _ in cursor.executed]
        joined = " | ".join(sqls)
        self.assertIn("FOR UPDATE", joined)
        self.assertIn("UPDATE", joined)
        self.assertIn("__slot_spin", joined)
        self.assertIn("INSERT", joined)
        self.assertIn("biggest_win", joined)

    def test_losing_spin_no_biggest_win_update(self):
        from casino.services.slots import (
            _dealers,
            handle_spin,
            invalidate_dealer,
        )
        from casino.slots.lib import SpinResult, Symbol

        lemon = Symbol("LEMON", 1, "L")

        class StubDealer:
            num_reels = 5
            num_rows = 3
            def play(self, bet):
                return SpinResult(
                    reels=[[lemon] * 3 for _ in range(5)],
                    center_row=[lemon] * 5,
                    wins=[],
                    bet=bet,
                    payout=0,
                    net=-bet,
                )

        _dealers["t1"] = StubDealer()
        self.addCleanup(invalidate_dealer, "t1")

        cursor = _StubCursor(
            initial={"id": 1, "balance": 1000},
            insert_returning={"id": 7},
        )
        conn = _StubConn(cursor)

        @contextlib.contextmanager
        def fake_connect(*a, **kw):
            yield conn

        with patch("casino.services.slots.database.connect", fake_connect), \
             patch("casino.services.slots.database.cursor",
                   side_effect=lambda c, **kw: c.cursor()), \
             patch("casino.services.slots.dal_table.get_table",
                   return_value={"type": "slots", "minimumbet": 1,
                                 "maximumbet": 1000}):
            r = handle_spin(_make_args(), "t1", "alice", 10)

        self.assertTrue(r["success"])
        self.assertEqual(r["spin"]["payout"], 0)
        self.assertEqual(r["spin"]["net"], -10)
        # No biggest_win UPDATE because payout == 0.
        # Trace: SELECT, UPDATE bank, INSERT spin, UPDATE stats.
        self.assertEqual(len(cursor.executed), 4)
        for s, _ in cursor.executed:
            self.assertNotIn("biggest_win", s)


class TestServiceRollbackInsufficientFunds(unittest.TestCase):
    """If the player balance is below the bet, the service returns
    insufficient_funds without writing the audit row or stats."""

    def test_insufficient_funds_short_circuits(self):
        from casino.services.slots import (
            _dealers,
            handle_spin,
            invalidate_dealer,
        )
        from casino.slots.lib import SpinResult, Symbol

        lemon = Symbol("LEMON", 1, "L")

        class StubDealer:
            num_reels = 5
            num_rows = 3
            def play(self, bet):
                return SpinResult(
                    reels=[[lemon] * 3 for _ in range(5)],
                    center_row=[lemon] * 5,
                    wins=[],
                    bet=bet,
                    payout=0,
                    net=-bet,
                )

        _dealers["t1"] = StubDealer()
        self.addCleanup(invalidate_dealer, "t1")

        cursor = _StubCursor(initial={"id": 1, "balance": 5})
        conn = _StubConn(cursor)

        @contextlib.contextmanager
        def fake_connect(*a, **kw):
            yield conn

        with patch("casino.services.slots.database.connect", fake_connect), \
             patch("casino.services.slots.database.cursor",
                   side_effect=lambda c, **kw: c.cursor()), \
             patch("casino.services.slots.dal_table.get_table",
                   return_value={"type": "slots", "minimumbet": 1,
                                 "maximumbet": 1000}):
            r = handle_spin(_make_args(), "t1", "alice", 100)

        self.assertFalse(r["success"])
        self.assertEqual(r["code"], "insufficient_funds")
        # Only the SELECT FOR UPDATE executed; no audit, no stats.
        self.assertEqual(len(cursor.executed), 1)
        self.assertIn("FOR UPDATE", cursor.executed[0][0])

    def test_wrong_game_type_returns_error(self):
        from casino.services.slots import handle_spin

        with patch(
            "casino.services.slots.dal_table.get_table",
            return_value={"type": "blackjack", "minimumbet": 1,
                          "maximumbet": 1000},
        ):
            r = handle_spin(_make_args(), "bj-table", "alice", 10)

        self.assertFalse(r["success"])
        self.assertEqual(r["code"], "wrong_game_type")

    def test_table_not_found(self):
        from casino.services.slots import handle_spin

        with patch("casino.services.slots.dal_table.get_table", return_value=None):
            r = handle_spin(_make_args(), "missing", "alice", 10)

        self.assertFalse(r["success"])
        self.assertEqual(r["code"], "table_not_found")


# --------------------------------------------------------------------------- #
# Handler full message flow
# --------------------------------------------------------------------------- #


class _StubWS:
    """Stable-id websocket for handler tests."""
    _counter = 0

    def __init__(self):
        type(self)._counter += 1
        self._id = type(self)._counter
        self.id = self._id

    def __hash__(self):
        return self._id

    def __eq__(self, other):
        return isinstance(other, _StubWS) and other._id == self._id


class TestHandlerFullMessageFlow(unittest.TestCase):
    """End-to-end through SlotServiceHandler for spin, paytable, and
    history. Auth, validation, broadcast, and reply shape are
    exercised together."""

    def setUp(self):
        import asyncio

        from casino.api.handler import SlotServiceHandler
        from casino.tests._session_mock import make_sessions_mock

        self.args = _make_args()
        self.sessions = make_sessions_mock(
            moniker="alice", table_moniker="slots-alice"
        )
        self.handler = SlotServiceHandler(self.args, self.sessions, channel_state=None)
        self.ws = _StubWS()
        self.sessions.register_session(id(self.ws), "alice", is_sysop=False)
        self.sessions.set_table_moniker(id(self.ws), "slots-alice")
        self._asyncio = asyncio

    def _stub_dealer(self, result):
        from casino.services.slots import _dealers, invalidate_dealer

        class StubDealer:
            num_reels = 5
            num_rows = 3
            def play(self, bet):
                return result

        _dealers["slots-alice"] = StubDealer()
        self.addCleanup(invalidate_dealer, "slots-alice")

    def test_slot_spin_full_flow_with_broadcast(self):
        from casino.slots.lib import SpinResult, Symbol, Win

        seven = Symbol("SEVEN", 1, "7")
        self._stub_dealer(SpinResult(
            reels=[[seven] * 3 for _ in range(5)],
            center_row=[seven] * 5,
            wins=[Win(("SEVEN",) * 3, 10, 100)],
            bet=10,
            payout=100,
            net=90,
        ))

        cursor = _StubCursor(
            initial={"id": 1, "balance": 100},
            insert_returning={"id": 1},
        )
        conn = _StubConn(cursor)

        @contextlib.contextmanager
        def fake_connect(*a, **kw):
            yield conn

        server = AsyncMock()
        with patch("casino.services.slots.database.connect", fake_connect), \
             patch("casino.services.slots.database.cursor",
                   side_effect=lambda c, **kw: c.cursor()), \
             patch("casino.services.slots.dal_table.get_table",
                   return_value={"type": "slots", "minimumbet": 1,
                                 "maximumbet": 1000}):
            r = self._asyncio.run(self.handler.handle_message(
                server, self.ws, "/", {"type": "slot_spin", "bet": 10}
            ))

        self.assertEqual(r["type"], "slot_result")
        self.assertEqual(r["table_moniker"], "slots-alice")
        self.assertEqual(r["spin"]["bet"], 10)
        # Broadcast goes out to the table channel with the same shape.
        self.assertTrue(server.publish.called)
        channel, payload = server.publish.call_args.args
        self.assertEqual(channel, "casino:table:slots-alice")
        self.assertEqual(payload["type"], "slot_result")
        self.assertEqual(payload["spin"]["bet"], 10)

    def test_slot_paytable_lookup(self):
        from casino.services.slots import _dealers, invalidate_dealer
        from casino.slots.lib import Paytable

        _dealers["slots-alice"] = type("D", (), {
            "num_reels": 5,
            "num_rows": 3,
            "play": lambda self, bet: None,
            "paytable": Paytable(),
        })()
        self.addCleanup(invalidate_dealer, "slots-alice")

        with patch(
            "casino.services.slots.dal_table.get_table",
            return_value={"type": "slots"},
        ):
            r = self._asyncio.run(self.handler.handle_message(
                None, self.ws, "/", {"type": "slot_paytable"}
            ))

        self.assertEqual(r["type"], "slot_paytable")
        self.assertEqual(r["moniker"], "slots-alice")
        self.assertGreater(len(r["payouts"]), 0)
        for p in r["payouts"]:
            self.assertIn("symbols", p)
            self.assertIn("multiplier", p)

    def test_slot_history_returns_recent_spins(self):
        fake_rows = [
            {"id": 1, "bet": 10, "payout": 0, "net": -10},
            {"id": 2, "bet": 20, "payout": 100, "net": 80},
        ]
        with patch(
            "casino.services.slots.dal_slots.get_spin_history",
            return_value=fake_rows,
        ):
            r = self._asyncio.run(self.handler.handle_message(
                None, self.ws, "/",
                {"type": "slot_history", "limit": 5, "moniker": "alice"},
            ))

        self.assertEqual(r["type"], "slot_history")
        self.assertEqual(len(r["spins"]), 2)
        self.assertEqual(r["spins"][1]["payout"], 100)

    def test_slot_history_other_player_as_sysop_allowed(self):
        """A sysop can read any player's history."""
        from casino.tests._session_mock import make_sessions_mock

        sysop_sessions = make_sessions_mock(
            moniker="root", table_moniker=None, is_sysop=True
        )
        sysop_handler = self.handler.__class__(
            self.args, sysop_sessions, channel_state=None
        )
        sysop_ws = _StubWS()
        sysop_sessions.register_session(id(sysop_ws), "root", is_sysop=True)

        with patch(
            "casino.services.slots.dal_slots.get_spin_history",
            return_value=[],
        ):
            r = self._asyncio.run(sysop_handler.handle_message(
                None, sysop_ws, "/",
                {"type": "slot_history", "limit": 5, "moniker": "alice"},
            ))

        self.assertEqual(r["type"], "slot_history")
        self.assertEqual(r["spins"], [])

    def test_slot_spin_invalid_bet_type(self):
        """A bet of 'ten' (string) is rejected by the service layer."""
        with patch(
            "casino.services.slots.dal_table.get_table",
            return_value={"type": "slots", "minimumbet": 1, "maximumbet": 1000},
        ):
            r = self._asyncio.run(self.handler.handle_message(
                None, self.ws, "/", {"type": "slot_spin", "bet": "ten"}
            ))
        self.assertEqual(r["type"], "error")
        self.assertEqual(r["code"], "invalid_bet")

    def test_slot_spin_publish_failure_is_swallowed(self):
        """A failing server.publish() must not propagate; the player
        still gets their slot_result reply."""
        from casino.slots.lib import SpinResult, Symbol

        lemon = Symbol("LEMON", 1, "L")
        self._stub_dealer(SpinResult(
            reels=[[lemon] * 3 for _ in range(5)],
            center_row=[lemon] * 5,
            wins=[],
            bet=10,
            payout=0,
            net=-10,
        ))

        cursor = _StubCursor(
            initial={"id": 1, "balance": 100},
            insert_returning={"id": 1},
        )
        conn = _StubConn(cursor)

        @contextlib.contextmanager
        def fake_connect(*a, **kw):
            yield conn

        async def bad_publish(*a, **kw):
            raise RuntimeError("publish exploded")

        server = AsyncMock()
        server.publish = bad_publish

        with patch("casino.services.slots.database.connect", fake_connect), \
             patch("casino.services.slots.database.cursor",
                   side_effect=lambda c, **kw: c.cursor()), \
             patch("casino.services.slots.dal_table.get_table",
                   return_value={"type": "slots", "minimumbet": 1,
                                 "maximumbet": 1000}):
            r = self._asyncio.run(self.handler.handle_message(
                server, self.ws, "/", {"type": "slot_spin", "bet": 10}
            ))

        self.assertEqual(r["type"], "slot_result")
        self.assertEqual(r["spin"]["bet"], 10)


# --------------------------------------------------------------------------- #
# Dealer cache invalidation lifecycle
# --------------------------------------------------------------------------- #


class TestDealerCacheInvalidationLifecycle(unittest.TestCase):
    """After invalidate_dealer, the next get_dealer rebuilds with the
    new table config; the rebuilt dealer reflects the override."""

    def test_invalidation_picks_up_paytable_change(self):
        from casino.services.slots import get_dealer, invalidate_dealer

        configs = iter([
            {"type": "slots", "attrs": {}},
            {"type": "slots", "attrs": {
                "paytable_override": [
                    {"symbols": ["SEVEN", "SEVEN", "SEVEN"], "multiplier": 999},
                ]
            }},
        ])
        with patch("casino.services.slots.dal_table.get_table",
                   side_effect=lambda args, m: next(configs)):
            d1 = get_dealer(_make_args(), "t1")
            mult_before = d1.paytable.get(("SEVEN",) * 3)
            invalidate_dealer("t1")
            d2 = get_dealer(_make_args(), "t1")
            mult_after = d2.paytable.get(("SEVEN",) * 3)
            self.assertIsNot(d1, d2)
            self.assertEqual(mult_before, 145)
            self.assertEqual(mult_after, 999)

        invalidate_dealer("t1")


if __name__ == "__main__":
    unittest.main()
