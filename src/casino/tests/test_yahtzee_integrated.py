#!/usr/bin/env python3
# casino/tests/test_yahtzee_integrated.py
# Comprehensive end-to-end integration tests for the yahtzee subsystem.
#
# These tests exercise the full stack without a live PostgreSQL: dealer
# state machine, scoring across all 13 categories, the door-mode play
# loop, the service-layer turn flow (mocked dal), and the BED
# handler's WebSocket message dispatch + broadcast. They run under
# the same pytest invocation as the rest of the casino suite, with
# no CASINO_TEST_DB env var required.
#
# Coverage map:
#   TestFullGameScenario               13 rounds, deterministic dice, end state
#   TestLockStateMachine               locks preserved across reroll, un-lock clears
#   TestScoringIntegration             every category scored against canonical dice
#   TestServiceFlowWithFakeDB          quick_play -> roll -> reroll -> score SQL trace
#   TestDoorModePlayLoopEndToEnd       play.main() across all 13 rounds with mock io
#   TestDisconnectAndFinalize          finalize_on_disconnect settles loss + cancels
#   TestYahtzeeBonusCases              yahtzee scoring + joker-rule consistency
#   TestDealerAndPlayerLifecycle       dealer.reroll edge cases, player validation

import argparse
import contextlib
import random
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, "/home/opencode/data/work/casino/src")
sys.path.insert(0, "/home/opencode/data/work/casino/src/casino/tests")


def _make_args(**overrides):
    base = {"databasename": "test", "database": "test", "debug": False}
    base.update(overrides)
    return argparse.Namespace(**base)


# --------------------------------------------------------------------------- #
# Service fixture helpers (mirrors test_yahtzee_service.py conventions)
# --------------------------------------------------------------------------- #


def _make_service(seed=0, find_returns=None):
    """YahtzeeService with all DB-touching deps mocked out."""
    from casino.yahtzee.dealer import YahtzeeDealer
    from casino.yahtzee.service import YahtzeeService

    ts = MagicMock()
    ts.create_table.return_value = {
        "success": True,
        "table": {
            "moniker": "yahtzee-alice", "type": "yahtzee",
            "minimumbet": 10, "maximumbet": 1000,
            "ownermoniker": "alice", "status": "open",
            "hidden": True, "accountid": 1,
        },
        "message": "ok",
    }
    dealer = YahtzeeDealer(rng=random.Random(seed))
    find_fn = MagicMock(return_value=find_returns)
    return YahtzeeService(
        _make_args(), dealer=dealer, table_service=ts, find_table_fn=find_fn,
    )


@contextlib.contextmanager
def _patched_db():
    """Patch casino.yahtzee.service dal_bet / dal_game / database.

    Yields (db, dg, dbconn) MagicMock tuples so the test can inspect
    calls. The mocks default to "id 42" for create_game and "id 7"
    for place_bet.
    """
    db = MagicMock()
    dg = MagicMock()
    dbconn = MagicMock()
    dg.create_game.return_value = {"id": 42}
    db.place_bet.return_value = {"id": 7}

    p1 = patch("casino.yahtzee.service.dal_bet", db)
    p2 = patch("casino.yahtzee.service.dal_game", dg)
    p3 = patch("casino.yahtzee.service.database", dbconn)
    p1.start()
    p2.start()
    p3.start()
    try:
        yield db, dg, dbconn
    finally:
        p1.stop()
        p2.stop()
        p3.stop()


class _SimpleSQL:
    """Stand-in for psycopg's Composed SQL object: exposes ``.text``
    and ``.params`` so test assertions can introspect both halves
    without standing up a real connection."""

    __slots__ = ("text", "params")

    def __init__(self, text, params):
        self.text = text
        self.params = params

    def __str__(self):
        return self.text

    def __iter__(self):
        # Make _sql_text flatten us as a leaf, not a sequence.
        return iter([self.text])


class _StubCursor:
    """Tiny cursor fake: records every execute() call, hands out a
    fixed row on the first fetchone(). Mirrors what the yahtzee
    service's ``_write_turn_log`` needs."""

    def __init__(self, fetchone_value=None):
        self.fetchone_value = fetchone_value
        self.executed = []

    def execute(self, sql, params=None):
        # Some callers pass params via the SQL object (Composed),
        # which exposes them as .params. Normalize so downstream
        # assertions can subscript cursor.executed[i][1].
        if params is None and hasattr(sql, "params"):
            params = sql.params
        self.executed.append((sql, params))

    def fetchone(self):
        return self.fetchone_value

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _StubConn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self, *a, **kw):
        return self._cursor

    def commit(self):
        pass

    def rollback(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _sql_text(sql_obj) -> str:
    """Flatten a psycopg Composed/SQL object to a plain string."""
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
# TestFullGameScenario
# --------------------------------------------------------------------------- #


class TestFullGameScenario(unittest.TestCase):
    """Drive a 13-round game with a seeded RNG and score every round
    into the next category in order. Verify the final scorecard is
    fully filled, the grand total matches the sum of all scores,
    and the game registry removes the table once ``is_over``."""

    def test_full_13_round_session_with_deterministic_dice(self):
        from casino.yahtzee import lib

        s = _make_service(seed=20240101)
        s._dealer = MagicMock()
        # Dice for each round, paired with the CATEGORIES-in-order
        # category: every dice tuple scores non-zero in its paired
        # category so the spot-checks below have a clean expected
        # value. Categories_in_order: ones, twos, threes, fours,
        # fives, sixes, three_of_a_kind, four_of_a_kind,
        # full_house, small_straight, large_straight, yahtzee, chance.
        dice_per_round = [
            (1, 1, 1, 1, 1),  # 0 -> ones -> 5
            (2, 2, 2, 2, 2),  # 1 -> twos -> 10
            (3, 3, 3, 3, 3),  # 2 -> threes -> 15
            (4, 4, 4, 4, 4),  # 3 -> fours -> 20
            (5, 5, 5, 5, 5),  # 4 -> fives -> 25
            (6, 6, 6, 6, 6),  # 5 -> sixes -> 30
            (3, 3, 3, 4, 5),  # 6 -> three_of_a_kind -> 18
            (4, 4, 4, 4, 5),  # 7 -> four_of_a_kind -> 21
            (2, 2, 2, 1, 1),  # 8 -> full_house -> 25
            (3, 4, 5, 6, 1),  # 9 -> small_straight -> 30 (has 3-6)
            (1, 2, 3, 4, 5),  # 10 -> large_straight -> 40
            (2, 2, 2, 2, 2),  # 11 -> yahtzee -> 50
            (6, 6, 6, 6, 6),  # 12 -> chance -> 30
        ]
        s._dealer.fresh.side_effect = list(dice_per_round)
        # No rerolls in this scenario: reroll is identity.
        s._dealer.reroll.side_effect = lambda d, lk: d

        categories_in_order = list(lib.CATEGORIES)

        with _patched_db() as (db, dg, dbconn):
            state = s.quick_play("alice")
            self.assertEqual(state["round"], 0)
            self.assertEqual(state["dice"], [0, 0, 0, 0, 0])

            settle_calls = []
            db.settle_bet.side_effect = lambda *a, **kw: settle_calls.append(kw)

            for i, cat in enumerate(categories_in_order):
                rolled = s.roll("yahtzee-alice", "alice")
                self.assertEqual(rolled["dice"], list(dice_per_round[i]))
                self.assertEqual(rolled["rolls_left"], 1)
                result = s.score("yahtzee-alice", "alice", cat)
                if i < 12:
                    self.assertEqual(result["type"], "yahtzee_state")
                    self.assertEqual(result["round"], i + 1)
                else:
                    self.assertEqual(result["type"], "yahtzee_result")

            # 13 rounds -> 13 settle_bet calls (one per round)
            self.assertEqual(len(settle_calls), 13)
            for kw in settle_calls:
                self.assertEqual(kw["bet_id"], 7)
                self.assertIs(kw["won"], kw["payout"] > 0)

            # Game was popped from the registry on the final round
            self.assertIsNone(s.get_game("yahtzee-alice"))
            # Game status moved to "closed"
            dg.update_game_status.assert_called_once_with(
                s.args, 42, "closed"
            )

            # Final scorecard: every category filled (no None)
            self.assertEqual(result["upper_total"] + result["lower_total"],
                             result["grand_total"])
            for v in result["final_scorecard"].values():
                self.assertIsNotNone(v)

            # Spot-check scoring against the dice_per_round layout:
            # upper section: 5+10+15+20+25+30 = 105
            # lower section: 18+21+25+30+40+50+30 = 214
            # grand total = 319
            self.assertEqual(result["upper_total"], 105)
            self.assertEqual(result["lower_total"], 214)
            self.assertEqual(result["grand_total"], 319)
            self.assertEqual(result["final_scorecard"]["yahtzee"], 50)
            self.assertEqual(result["final_scorecard"]["full_house"], 25)
            self.assertEqual(result["final_scorecard"]["large_straight"], 40)
            self.assertEqual(result["final_scorecard"]["chance"], 30)


# --------------------------------------------------------------------------- #
# TestLockStateMachine
# --------------------------------------------------------------------------- #


class TestLockStateMachine(unittest.TestCase):
    """Locks must persist their face value across reroll, and must
    be cleared at the start of each new round."""

    def test_locks_preserve_values_across_reroll(self):
        from casino.yahtzee.dealer import YahtzeeDealer

        # Use a deterministic RNG so we can reason about the
        # unlocked dice positions specifically.
        dealer = YahtzeeDealer(rng=random.Random(42))
        # First roll: all sixes
        dice = (6, 6, 6, 6, 6)
        # Lock indices 0, 2, 4; reroll 1 and 3. With seed 42 those
        # should produce deterministic new values.
        locked = [True, False, True, False, True]
        new = dealer.reroll(dice, locked)
        self.assertEqual(new[0], 6)  # locked
        self.assertEqual(new[2], 6)  # locked
        self.assertEqual(new[4], 6)  # locked
        # Rerolled positions are 1-6 (we don't assert which, just
        # that they're not the original locked value across enough
        # runs; for one call we don't have a guarantee, so just
        # verify they're in range).
        self.assertIn(new[1], range(1, 7))
        self.assertIn(new[3], range(1, 7))

    def test_all_locked_reroll_keeps_all_values(self):
        from casino.yahtzee.dealer import YahtzeeDealer

        dealer = YahtzeeDealer(rng=random.Random(7))
        dice = (3, 4, 5, 2, 1)
        new = dealer.reroll(dice, [True] * 5)
        self.assertEqual(new, dice)

    def test_no_locked_reroll_replaces_all(self):
        """With no locks, the dealer returns an entirely new 5-tuple.
        We can't predict the values, but we can verify they're all
        in [1,6] and at least one differs from the input."""
        from casino.yahtzee.dealer import YahtzeeDealer

        dealer = YahtzeeDealer(rng=random.Random(99))
        dice = (1, 1, 1, 1, 1)
        new = dealer.reroll(dice, [False] * 5)
        self.assertEqual(len(new), 5)
        for d in new:
            self.assertIn(d, range(1, 7))
        # Statistically certain to differ for any 5-reroll seed.
        self.assertNotEqual(new, dice)

    def test_reroll_rejects_wrong_length(self):
        from casino.yahtzee.dealer import YahtzeeDealer

        dealer = YahtzeeDealer(rng=random.Random(0))
        with self.assertRaises(ValueError):
            dealer.reroll((1, 2, 3), [True, False, True])
        with self.assertRaises(ValueError):
            dealer.reroll((1, 2, 3, 4, 5), [True, False])

    def test_service_locks_reset_between_rounds(self):
        """A score() call clears the lock mask so the next round
        starts fresh."""
        s = _make_service(seed=1)
        s._dealer = MagicMock()
        s._dealer.fresh.side_effect = [
            (1, 1, 1, 1, 1),
            (2, 2, 2, 2, 2),
        ]
        s._dealer.reroll.side_effect = lambda d, lk: d

        with _patched_db():
            s.quick_play("alice")
            s.roll("yahtzee-alice", "alice")
            s.reroll("yahtzee-alice", "alice", [0, 1])
            state = s.score("yahtzee-alice", "alice", "ones")
            self.assertEqual(state["dice"], [0, 0, 0, 0, 0])
            self.assertEqual(state["locked"], [False] * 5)
            self.assertEqual(state["rolls_left"], 2)
            # Roll 2 again to verify locks don't leak
            rolled = s.roll("yahtzee-alice", "alice")
            self.assertEqual(rolled["dice"], [2, 2, 2, 2, 2])
            self.assertEqual(rolled["locked"], [False] * 5)


# --------------------------------------------------------------------------- #
# TestScoringIntegration
# --------------------------------------------------------------------------- #


class TestScoringIntegration(unittest.TestCase):
    """For every category, a canonical dice combo scores exactly the
    documented yahtzee value. These are the integration regression
    tests for ``lib.score`` against real combinations."""

    def test_upper_section_face_sums(self):
        from casino.yahtzee.lib import score

        # 5x three = 15
        self.assertEqual(score([3, 3, 3, 3, 3], "threes"), 15)
        # 4x six = 24 (two of the six are not six)
        self.assertEqual(score([6, 6, 6, 6, 2], "sixes"), 24)
        # No twos = 0
        self.assertEqual(score([1, 3, 4, 5, 6], "twos"), 0)

    def test_three_of_a_kind_is_dice_total(self):
        from casino.yahtzee.lib import score

        # 3x four + 2,5 -> 4+4+4+2+5 = 19
        self.assertEqual(score([4, 4, 4, 2, 5], "three_of_a_kind"), 19)
        # No three of a kind -> 0
        self.assertEqual(score([1, 2, 3, 4, 5], "three_of_a_kind"), 0)

    def test_four_of_a_kind_is_dice_total(self):
        from casino.yahtzee.lib import score

        self.assertEqual(score([5, 5, 5, 5, 2], "four_of_a_kind"), 22)
        self.assertEqual(score([1, 2, 3, 4, 5], "four_of_a_kind"), 0)

    def test_full_house_fixed_25(self):
        from casino.yahtzee.lib import score

        self.assertEqual(score([2, 2, 2, 3, 3], "full_house"), 25)
        self.assertEqual(score([1, 2, 3, 4, 5], "full_house"), 0)

    def test_small_straight_high_4_5_6(self):
        from casino.yahtzee.lib import score

        # 1,2,3,4 -> small_straight (high 4) = 30
        self.assertEqual(score([1, 2, 3, 4, 6], "small_straight"), 30)
        # 2,3,4,5 -> high 5 = 30
        self.assertEqual(score([2, 3, 4, 5, 6], "small_straight"), 30)
        # 3,4,5,6 -> high 6 = 30
        self.assertEqual(score([1, 3, 4, 5, 6], "small_straight"), 30)
        # No 4-run = 0
        self.assertEqual(score([1, 2, 4, 5, 6], "small_straight"), 0)

    def test_large_straight_fixed_40(self):
        from casino.yahtzee.lib import score

        self.assertEqual(score([1, 2, 3, 4, 5], "large_straight"), 40)
        self.assertEqual(score([2, 3, 4, 5, 6], "large_straight"), 40)
        self.assertEqual(score([1, 2, 3, 4, 6], "large_straight"), 0)

    def test_yahtzee_fixed_50(self):
        from casino.yahtzee.lib import score

        self.assertEqual(score([4, 4, 4, 4, 4], "yahtzee"), 50)
        # Five distinct = not yahtzee -> 0
        self.assertEqual(score([1, 2, 3, 4, 5], "yahtzee"), 0)

    def test_chance_is_dice_total(self):
        from casino.yahtzee.lib import score

        self.assertEqual(score([6, 6, 6, 6, 6], "chance"), 30)
        self.assertEqual(score([1, 2, 3, 4, 5], "chance"), 15)

    def test_score_rejects_unknown_category(self):
        from casino.yahtzee.lib import score

        with self.assertRaises(ValueError):
            score([1, 2, 3, 4, 5], "five_of_a_kind")

    def test_score_rejects_wrong_dice_length(self):
        from casino.yahtzee.lib import score

        with self.assertRaises(ValueError):
            score([1, 2, 3, 4], "chance")

    def test_suggest_returns_all_13_categories(self):
        from casino.yahtzee.lib import CATEGORIES, suggest

        out = suggest([1, 1, 1, 1, 1])
        self.assertEqual(set(out.keys()), set(CATEGORIES))
        # All 1s: ones=5, yahtzee=50, everything else=0
        self.assertEqual(out["ones"], 5)
        self.assertEqual(out["yahtzee"], 50)
        self.assertEqual(out["twos"], 0)
        self.assertEqual(out["full_house"], 0)
        self.assertEqual(out["chance"], 5)


# --------------------------------------------------------------------------- #
# TestServiceFlowWithFakeDB
# --------------------------------------------------------------------------- #


class TestServiceFlowWithFakeDB(unittest.TestCase):
    """End-to-end through the YahtzeeService for one round, with all
    DB calls routed to a cursor fake so we can inspect the SQL
    trace. Mirrors test_slots_flow.py."""

    def test_one_round_full_trace(self):
        s = _make_service(seed=4)
        s._dealer = MagicMock()
        s._dealer.fresh.return_value = (1, 1, 1, 1, 1)
        s._dealer.reroll.side_effect = lambda d, lk: d

        cursor = _StubCursor()
        conn = _StubConn(cursor)

        @contextlib.contextmanager
        def fake_connect(*a, **kw):
            yield conn

        with _patched_db() as (db, dg, dbconn):
            dbconn.connect.side_effect = fake_connect
            dbconn.cursor.return_value = cursor
            # database.query is used to build the SQL string; return a
            # simple namespace exposing both text and params so the
            # cursor records a real string (and params) we can grep.
            def _query(sql, **kw):
                return _SimpleSQL(sql, kw)
            dbconn.query.side_effect = _query

            quick = s.quick_play("alice")
            self.assertEqual(quick["round"], 0)
            self.assertEqual(quick["rolls_left"], 2)
            self.assertEqual(quick["last_score"], 0)
            # quick_play writes one row via create_game + place_bet
            self.assertEqual(dg.create_game.call_count, 1)
            self.assertEqual(db.place_bet.call_count, 1)

            rolled = s.roll("yahtzee-alice", "alice")
            self.assertEqual(rolled["dice"], [1, 1, 1, 1, 1])
            self.assertEqual(rolled["rolls_left"], 1)

            # Score the yahtzee into "ones" (a non-yahtzee category)
            # so we verify the dice_total path of upper section
            # scoring. ones=5 with 5x1s.
            result = s.score("yahtzee-alice", "alice", "ones")
            self.assertEqual(result["type"], "yahtzee_state")
            self.assertEqual(result["round"], 1)
            self.assertEqual(result["last_score"], 5)

            # settle_bet called once with won=True, payout=5
            db.settle_bet.assert_called_once()
            call = db.settle_bet.call_args.kwargs
            self.assertEqual(call["bet_id"], 7)
            self.assertEqual(call["payout"], 5)
            self.assertTrue(call["won"])

            # One __log row written for the turn
            self.assertEqual(len(cursor.executed), 1)
            sql = _sql_text(cursor.executed[0][0])
            self.assertIn("__log", sql)
            self.assertEqual(cursor.executed[0][1]["message"], "yahtzee_turn")
            self.assertEqual(cursor.executed[0][1]["table_moniker"], "yahtzee-alice")

    def test_quick_play_writes_game_then_bet(self):
        """The order matters: create_game must come before
        place_bet, because place_bet references game_id."""
        s = _make_service(find_returns=None)
        call_log = []

        with _patched_db() as (db, dg, dbconn):
            original_cg = dg.create_game.side_effect
            original_pb = db.place_bet.side_effect

            def trace_cg(*a, **kw):
                call_log.append("create_game")
                return {"id": 42}

            def trace_pb(*a, **kw):
                call_log.append("place_bet")
                return {"id": 7}

            dg.create_game.side_effect = trace_cg
            db.place_bet.side_effect = trace_pb

            s.quick_play("alice")
            self.assertEqual(call_log, ["create_game", "place_bet"])

    def test_reroll_with_locks_uses_dice_total(self):
        s = _make_service(seed=8)
        s._dealer = MagicMock()
        # Initial roll: (1, 1, 1, 1, 6). Reroll with [4] locked
        # (the six) keeps index 4, rerolls others.
        s._dealer.fresh.return_value = (1, 1, 1, 1, 6)
        # After reroll: index 4 still 6, others random. Use a fixed
        # sequence so the result is deterministic.
        s._dealer.reroll.return_value = (2, 3, 4, 5, 6)

        with _patched_db():
            s.quick_play("alice")
            s.roll("yahtzee-alice", "alice")
            state = s.reroll("yahtzee-alice", "alice", [4])
            self.assertEqual(state["dice"], [2, 3, 4, 5, 6])
            self.assertEqual(state["locked"], [False, False, False, False, True])
            self.assertEqual(state["rolls_left"], 0)
            # Lock index 4 was passed in: verify the dealer saw it
            s._dealer.reroll.assert_called_once()
            args, _ = s._dealer.reroll.call_args
            self.assertEqual(args[0], (1, 1, 1, 1, 6))
            self.assertEqual(args[1], [False, False, False, False, True])


# --------------------------------------------------------------------------- #
# TestDisconnectAndFinalize
# --------------------------------------------------------------------------- #


class TestDisconnectAndFinalize(unittest.TestCase):
    """finalize_on_disconnect must settle the open bet as a loss,
    mark the __game cancelled, and remove the game from the
    registry. Calling it twice is safe."""

    def test_finalize_settles_loss_and_cancels_game(self):
        s = _make_service()
        with _patched_db() as (db, dg, _dbconn):
            s.quick_play("alice")
            self.assertIsNotNone(s.get_game("yahtzee-alice"))
            result = s.finalize_on_disconnect("yahtzee-alice")
            self.assertTrue(result)
            db.settle_bet.assert_called_once_with(
                s.args, bet_id=7, won=False, payout=0,
            )
            dg.update_game_status.assert_called_once_with(
                s.args, 42, "cancelled",
            )
            self.assertIsNone(s.get_game("yahtzee-alice"))

    def test_finalize_idempotent(self):
        """A second call after the game is gone returns False and
        does not touch the DB."""
        s = _make_service()
        with _patched_db() as (db, dg, _dbconn):
            s.quick_play("alice")
            s.finalize_on_disconnect("yahtzee-alice")
            db.settle_bet.reset_mock()
            dg.update_game_status.reset_mock()
            result = s.finalize_on_disconnect("yahtzee-alice")
            self.assertFalse(result)
            db.settle_bet.assert_not_called()
            dg.update_game_status.assert_not_called()

    def test_finalize_unknown_table_returns_false(self):
        s = _make_service()
        self.assertFalse(s.finalize_on_disconnect("does-not-exist"))


# --------------------------------------------------------------------------- #
# TestDoorModePlayLoopEndToEnd
# --------------------------------------------------------------------------- #


class TestDoorModePlayLoopEndToEnd(unittest.TestCase):
    """Drive ``yahtzee.play.main`` through all 13 rounds by mocking
    inputchoice / inputstring. The play loop uses uppercase option
    keys for the action prompt (``rlsq``) and lowercase letter
    shortcuts for the category prompt (``abcdefghijklm``). We feed
    pre-canned keypresses; the dealer is real and deterministic.

    Note: ``bbsengine6.io.common.get_cursor_position`` is mocked
    because inputstring queries the real terminal cursor via DSR;
    pytest's redirected stdin has no ``fileno()``.
    """

    def _enter_common(self, stack):
        return [
            stack.enter_context(patch(
                "bbsengine6.io.common.get_cursor_position",
                return_value=(1, 1),
            )),
            stack.enter_context(patch("casino.yahtzee.play.io.echo")),
            stack.enter_context(patch("casino.yahtzee.play.util.heading")),
        ]

    def test_full_game_play_through_13_rounds(self):
        from casino.yahtzee.dealer import YahtzeeDealer
        from casino.yahtzee.player import YahtzeePlayer

        # Deterministic dealer: every fresh() returns the same dice
        # tuple so we can predict scores. Each round: roll once,
        # score into a *different* category (a..m) so the score
        # prompt doesn't reject a duplicate letter.
        dealer = YahtzeeDealer(rng=random.Random(7))
        player = YahtzeePlayer(
            moniker="alice", credits=1000, bet_amount=10,
            min_bet=10, max_bet=1000,
        )

        # Action prompt is "rlsq" with default "r"; the play loop
        # upper-cases user input. The score prompt is the 13 letters
        # "abcdefghijklm" with default "c". We feed "R" for roll,
        # "S" for score, then a different category letter per round.
        # 13 rounds * (R + S + letter) = 39 inputchoice calls.
        letters = list("abcdefghijklm")
        ic_q = []
        for letter in letters:
            ic_q.extend(["R", "S", letter])

        with contextlib.ExitStack() as stack:
            mock_ic = stack.enter_context(patch(
                "casino.yahtzee.play.io.inputchoice", side_effect=ic_q))
            self._enter_common(stack)
            from casino.yahtzee import play
            result = play.main(_make_args(), player=player, dealer=dealer)

        self.assertTrue(result)
        self.assertEqual(player.round_idx, 13)
        self.assertTrue(player.is_over)
        # 3 calls per round x 13 rounds = 39 inputchoice calls
        self.assertEqual(mock_ic.call_count, 39)
        # Each inputchoice call must have help= wired
        for c in mock_ic.call_args_list:
            self.assertIn("help", c.kwargs)
            self.assertTrue(callable(c.kwargs["help"]))
        # All 13 categories filled with non-None scores
        for v in player.scorecard.values():
            self.assertIsNotNone(v)
        # Grand total is positive
        self.assertGreater(player.grand_total(), 0)

    def test_quit_action_ends_session_before_13_rounds(self):
        """Picking ``Q`` at the action prompt exits the loop
        immediately, leaving the scorecard partially filled."""
        from casino.yahtzee.dealer import YahtzeeDealer
        from casino.yahtzee.player import YahtzeePlayer

        dealer = YahtzeeDealer(rng=random.Random(0))
        player = YahtzeePlayer(
            moniker="alice", credits=1000, bet_amount=10,
            min_bet=10, max_bet=1000,
        )
        # Two rolls, then quit. Use different category letters so
        # the score prompt never rejects.
        ic_q = ["R", "S", "a", "R", "S", "b", "Q"]

        with contextlib.ExitStack() as stack:
            mock_ic = stack.enter_context(patch(
                "casino.yahtzee.play.io.inputchoice", side_effect=ic_q))
            self._enter_common(stack)
            from casino.yahtzee import play
            result = play.main(_make_args(), player=player, dealer=dealer)

        self.assertTrue(result)
        self.assertEqual(player.round_idx, 2)
        self.assertFalse(player.is_over)
        # 3 + 3 + 1 (quit) = 7 inputchoice calls
        self.assertEqual(mock_ic.call_count, 7)
        # Both scored categories are filled
        self.assertIsNotNone(player.scorecard["ones"])
        self.assertIsNotNone(player.scorecard["twos"])

    def test_repeated_category_is_rejected(self):
        """Scoring into a category that is already filled is
        rejected by the score prompt; the player must pick
        another letter."""
        from casino.yahtzee.dealer import YahtzeeDealer
        from casino.yahtzee.player import YahtzeePlayer

        dealer = YahtzeeDealer(rng=random.Random(0))
        player = YahtzeePlayer(
            moniker="alice", credits=1000, bet_amount=10,
            min_bet=10, max_bet=1000,
        )
        # Round 1: R, S, "a" (ones) -> accepted, ones is filled.
        # Round 2: R, S, "a" -> rejected (already filled), "b"
        # (twos) -> accepted.
        # Q at end -> loop exits before round 3 begins.
        ic_q = ["R", "S", "a", "R", "S", "a", "b", "Q"]

        with contextlib.ExitStack() as stack:
            mock_ic = stack.enter_context(patch(
                "casino.yahtzee.play.io.inputchoice", side_effect=ic_q))
            self._enter_common(stack)
            from casino.yahtzee import play
            play.main(_make_args(), player=player, dealer=dealer)

        self.assertEqual(player.round_idx, 2)
        self.assertIsNotNone(player.scorecard["ones"])
        self.assertIsNotNone(player.scorecard["twos"])
        # 7 inputchoice calls + 1 quit = 8 total
        self.assertEqual(mock_ic.call_count, 8)

    def test_invalid_action_loops_until_valid(self):
        """If inputchoice returns an unknown key, inputchoice
        would normally re-prompt. We use uppercase keys to ensure
        each call lands in the option set; the play code never
        sees an invalid key in this scenario."""
        # This test exists to pin the contract: the play loop
        # only accepts R, L, S, Q for the action prompt. We verify
        # by tracing one round and checking call args.
        from casino.yahtzee.dealer import YahtzeeDealer
        from casino.yahtzee.player import YahtzeePlayer

        dealer = YahtzeeDealer(rng=random.Random(0))
        player = YahtzeePlayer(
            moniker="alice", credits=1000, bet_amount=10,
            min_bet=10, max_bet=1000,
        )
        # One full round: R, S, "a" (ones). After that the loop
        # continues, but we want to stop after 1 round, so we
        # follow with Q at the next action prompt.
        ic_q = ["R", "S", "a", "Q"]

        with contextlib.ExitStack() as stack:
            mock_ic = stack.enter_context(patch(
                "casino.yahtzee.play.io.inputchoice", side_effect=ic_q))
            self._enter_common(stack)
            from casino.yahtzee import play
            play.main(_make_args(), player=player, dealer=dealer)

        # The first two inputchoice calls were for the action prompt
        # (options "rlsq"); the third was for the score prompt
        # (options "abcdefghijklm"); the fourth was a quit action.
        self.assertEqual(mock_ic.call_args_list[0].args[1], "rlsq")
        self.assertEqual(mock_ic.call_args_list[1].args[1], "rlsq")
        self.assertEqual(mock_ic.call_args_list[2].args[1], "abcdefghijklm")
        self.assertEqual(mock_ic.call_args_list[3].args[1], "rlsq")


# --------------------------------------------------------------------------- #
# TestYahtzeeBonusCases
# --------------------------------------------------------------------------- #


class TestYahtzeeBonusCases(unittest.TestCase):
    """v1 yahtzee has no upper-section bonus and no joker rule
    (RAKE_PERCENT=0). These tests pin down the v1 contract:
    yahtzee scoring is fixed at 50, yahtzee scored with non-yahtzee
    dice is 0, and chance / total math are independent."""

    def test_yahtzee_score_is_50(self):
        from casino.yahtzee.lib import score

        for face in range(1, 7):
            dice = [face] * 5
            self.assertEqual(score(dice, "yahtzee"), 50)

    def test_yahtzee_with_non_yahtzee_dice_is_zero(self):
        from casino.yahtzee.lib import score

        # Four of a kind + extra: not a yahtzee
        self.assertEqual(score([4, 4, 4, 4, 3], "yahtzee"), 0)
        # All different: not a yahtzee
        self.assertEqual(score([1, 2, 3, 4, 5], "yahtzee"), 0)
        # Full house: not a yahtzee
        self.assertEqual(score([2, 2, 2, 3, 3], "yahtzee"), 0)

    def test_net_payout_equals_score_in_v1(self):
        """In v1 RAKE_PERCENT=0, so net_payout == score."""
        from casino.yahtzee.lib import net_payout, score

        for cat in ["ones", "twos", "chance", "yahtzee", "full_house",
                    "small_straight", "large_straight"]:
            self.assertEqual(net_payout(score([1, 2, 3, 4, 5], cat)),
                             score([1, 2, 3, 4, 5], cat))

    def test_grand_total_no_upper_bonus(self):
        """The v1 contract: grand_total is upper + lower, no
        35-point upper-section bonus even when upper >= 63."""
        from casino.yahtzee.lib import (
            CATEGORIES, grand_total, upper_total,
        )

        scorecard = {c: (i + 1) * 6 for i, c in enumerate(CATEGORIES[:6])}
        for c in CATEGORIES[6:]:
            scorecard[c] = 0
        # upper = (1+2+3+4+5+6)*6 = 126. Without the bonus,
        # grand_total must equal 126.
        self.assertEqual(upper_total(scorecard), 126)
        self.assertEqual(grand_total(scorecard), 126)


# --------------------------------------------------------------------------- #
# TestDealerAndPlayerLifecycle
# --------------------------------------------------------------------------- #


class TestDealerAndPlayerLifecycle(unittest.TestCase):
    """Smoke tests for the dealer / player construction and
    validation paths that the rest of the suite depends on."""

    def test_player_validates_bet_amount(self):
        from casino.yahtzee.player import YahtzeePlayer

        with self.assertRaises(ValueError):
            YahtzeePlayer(moniker="a", credits=100, bet_amount=5)  # below min
        with self.assertRaises(ValueError):
            YahtzeePlayer(moniker="a", credits=100, bet_amount=2000)  # above max
        with self.assertRaises(ValueError):
            YahtzeePlayer(moniker="a", credits=10, bet_amount=100)  # above credits
        # Happy path
        p = YahtzeePlayer(moniker="a", credits=100, bet_amount=10)
        self.assertEqual(p.bet_amount, 10)
        self.assertEqual(p.credits, 100)
        self.assertEqual(p.round_idx, 0)
        self.assertEqual(p.rolls_left, 2)

    def test_player_rejects_negative_credits(self):
        from casino.yahtzee.player import YahtzeePlayer

        with self.assertRaises(ValueError):
            YahtzeePlayer(moniker="a", credits=-1, bet_amount=10)

    def test_player_initial_scorecard_is_empty(self):
        from casino.yahtzee import lib as yahtzee_lib
        from casino.yahtzee.player import YahtzeePlayer

        p = YahtzeePlayer(moniker="a", credits=100, bet_amount=10)
        self.assertEqual(len(p.scorecard), len(yahtzee_lib.CATEGORIES))
        for v in p.scorecard.values():
            self.assertIsNone(v)

    def test_dealer_default_uses_secrets(self):
        """YahtzeeDealer() with no rng arg must work and produce
        dice in [1, 6]."""
        from casino.yahtzee.dealer import YahtzeeDealer

        dealer = YahtzeeDealer()
        dice = dealer.fresh()
        self.assertEqual(len(dice), 5)
        for d in dice:
            self.assertIn(d, range(1, 7))


# --------------------------------------------------------------------------- #
# TestHandlerFullMessageFlow
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
    """End-to-end through YahtzeeServiceHandler for quick_play,
    roll, reroll, score, plus broadcast. Auth, validation, error
    paths, and disconnect cleanup are exercised together."""

    def setUp(self):
        import asyncio

        from casino.tests._session_mock import make_sessions_mock
        from casino.yahtzee.api_handler import YahtzeeServiceHandler

        self.args = _make_args()
        self.sessions = make_sessions_mock(
            moniker="alice", table_moniker="yahtzee-alice",
        )
        self.service = _make_service(seed=0)
        self.handler = YahtzeeServiceHandler(
            self.args, self.sessions, service=self.service,
        )
        # Door-mode fixture: drive the handler without a real
        # ``secret`` / ``token_store`` / ``instance_id`` so the
        # token gate becomes a no-op and the session lookup is the
        # authoritative authorization source. The same flag is set
        # by ``test_slots_flow.py`` and ``test_slots_integrated.py``
        # for the parallel slots-fixture seam.
        self.handler.allow_legacy_session_only = True
        self.ws = _StubWS()
        self.sessions.register_session(id(self.ws), "alice", is_sysop=False)
        self.sessions.set_table_moniker(id(self.ws), "yahtzee-alice")
        self._asyncio = asyncio

    def test_quick_play_roll_reroll_score_broadcast(self):
        # MagicMock the dealer so we can pin dice outputs without
        # binding to YahtzeeDealer method objects.
        self.service._dealer = MagicMock()
        self.service._dealer.fresh.return_value = (1, 1, 1, 1, 1)
        self.service._dealer.reroll.return_value = (1, 1, 1, 1, 1)

        server = AsyncMock()
        with _patched_db() as (_db, _dg, _dbconn):
            # quick_play
            r1 = self._asyncio.run(self.handler.handle_message(
                server, self.ws, "/", {"type": "yahtzee_quick_play"},
            ))
            self.assertEqual(r1["type"], "yahtzee_state")
            self.assertEqual(r1["round"], 0)
            # roll
            r2 = self._asyncio.run(self.handler.handle_message(
                server, self.ws, "/", {"type": "yahtzee_roll"},
            ))
            self.assertEqual(r2["type"], "yahtzee_state")
            self.assertEqual(r2["dice"], [1, 1, 1, 1, 1])
            self.assertEqual(r2["rolls_left"], 1)
            # reroll with no locks: dice unchanged (we returned the same)
            r3 = self._asyncio.run(self.handler.handle_message(
                server, self.ws, "/", {"type": "yahtzee_reroll", "locks": []},
            ))
            self.assertEqual(r3["type"], "yahtzee_state")
            self.assertEqual(r3["rolls_left"], 0)
            # score into chance
            r4 = self._asyncio.run(self.handler.handle_message(
                server, self.ws, "/",
                {"type": "yahtzee_score", "category": "chance"},
            ))
            self.assertEqual(r4["type"], "yahtzee_state")
            self.assertEqual(r4["round"], 1)
            self.assertEqual(r4["last_score"], 5)

        # Every state change was broadcast to the table channel.
        self.assertEqual(server.publish.await_count, 4)
        for call in server.publish.await_args_list:
            self.assertEqual(call.args[0], "casino:table:yahtzee-alice")
            self.assertIn(call.args[1]["type"],
                          ("yahtzee_state", "yahtzee_result"))

    def test_reroll_with_non_int_locks_is_bad_locks(self):
        self.service._dealer = MagicMock()
        self.service._dealer.fresh.return_value = (1, 1, 1, 1, 1)
        self.service._dealer.reroll.return_value = (1, 1, 1, 1, 1)

        with _patched_db():
            self._asyncio.run(self.handler.handle_message(
                None, self.ws, "/", {"type": "yahtzee_quick_play"},
            ))
            self._asyncio.run(self.handler.handle_message(
                None, self.ws, "/", {"type": "yahtzee_roll"},
            ))
            result = self._asyncio.run(self.handler.handle_message(
                None, self.ws, "/",
                {"type": "yahtzee_reroll", "locks": ["a", "b"]},
            ))
        self.assertEqual(result["type"], "error")
        self.assertEqual(result["code"], "bad_locks")

    def test_score_with_non_string_category_is_bad_category(self):
        self.service._dealer = MagicMock()
        self.service._dealer.fresh.return_value = (1, 1, 1, 1, 1)

        with _patched_db():
            self._asyncio.run(self.handler.handle_message(
                None, self.ws, "/", {"type": "yahtzee_quick_play"},
            ))
            self._asyncio.run(self.handler.handle_message(
                None, self.ws, "/", {"type": "yahtzee_roll"},
            ))
            result = self._asyncio.run(self.handler.handle_message(
                None, self.ws, "/",
                {"type": "yahtzee_score", "category": 42},
            ))
        self.assertEqual(result["type"], "error")
        self.assertEqual(result["code"], "bad_category")

    def test_publish_failure_is_swallowed(self):
        """A failing server.publish() must not propagate; the
        player still gets the yahtzee_state reply."""
        self.service._dealer = MagicMock()
        self.service._dealer.fresh.return_value = (1, 1, 1, 1, 1)

        async def bad_publish(*a, **kw):
            raise RuntimeError("publish exploded")

        server = AsyncMock()
        server.publish = bad_publish

        with _patched_db():
            r = self._asyncio.run(self.handler.handle_message(
                server, self.ws, "/", {"type": "yahtzee_quick_play"},
            ))
        self.assertEqual(r["type"], "yahtzee_state")
        self.assertEqual(r["round"], 0)

    def test_finalize_on_disconnect_via_handler(self):
        """The handler's ``finalize_on_disconnect`` hook settles
        the bet as a loss and removes the game from the registry."""
        self.service._dealer = MagicMock()
        self.service._dealer.fresh.return_value = (1, 1, 1, 1, 1)

        with _patched_db():
            self._asyncio.run(self.handler.handle_message(
                None, self.ws, "/", {"type": "yahtzee_quick_play"},
            ))
            self.assertIsNotNone(self.service.get_game("yahtzee-alice"))
            result = self.handler.finalize_on_disconnect("yahtzee-alice")
        self.assertTrue(result)
        self.assertIsNone(self.service.get_game("yahtzee-alice"))


if __name__ == "__main__":
    unittest.main()
