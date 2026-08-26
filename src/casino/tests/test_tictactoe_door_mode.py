# casino/tests/test_tictactoe_door_mode.py
# Tests for casino/tictactoe/__main__.py:_run_mode1 (door-mode single-player
# tic-tac-toe loop).
#
# Regression guard: prior to the fix, the door-mode ``PROMPT_OPTIONS``
# string was a human-readable label (``"[0-8]{f6}[Q]uit{f6}[R]esign"``) that
# also served as the ``options`` argument to ``io.inputchoice``. The label
# and options arguments are NOT interchangeable: ``inputchoice`` matches
# the typed key as a literal substring of ``options``. With the previous
# constant the literal characters ``1``-``7`` and ``9`` were not present,
# so pressing any of those keys rang the bell in an infinite re-prompt
# loop and never reached ``svc.play_move``. The regression is pinned by
# ``test_options_arg_is_tight_char_set`` and ``test_digit_*_dispatches``.

from unittest.mock import MagicMock, patch

import pytest

from casino.tictactoe import __main__ as tt_main


PLAYER = "alice"
TABLE_MONIKER = "ttt-alice"


def _initial_state():
    return {
        "type": "tictactoe_state",
        "table_moniker": TABLE_MONIKER,
        "mode": 1,
        "board": [0] * 9,
        "to_move": 1,
        "turn_moniker": PLAYER,
        "winner": None,
        "is_draw": False,
        "is_over": False,
        "last_move": None,
        "moves_played": 0,
    }


def _human_move_state(cell):
    state = _initial_state()
    state["board"][cell] = 1
    state["to_move"] = 2
    state["turn_moniker"] = "AI_O"
    state["last_move"] = {"cell": cell, "mark": 1, "by": PLAYER}
    state["moves_played"] = 1
    return state


def _make_svc(*, initial=None, move_returns=None, resign_returns=None):
    """Build a fake ``TictactoeService`` with stubbed methods.

    ``initial`` is the state returned by ``quick_play``. ``move_returns``
    is a list of states returned by successive ``play_move`` calls; the
    last entry (or a sentinel ending in a ``tictactoe_result``) terminates
    the loop. ``resign_returns`` is the state returned by ``resign``.
    """
    svc = MagicMock()
    svc.quick_play.return_value = initial if initial is not None else _initial_state()
    if move_returns is None:
        move_returns = [_human_move_state(4)]
    svc.play_move.side_effect = list(move_returns)

    if resign_returns is None:
        resign_returns = _initial_state()
    svc.resign.return_value = resign_returns
    return svc


def _echo_calls(mock_echo):
    """Flatten the echo calls into a list of (args, kwargs) pairs."""
    return mock_echo.call_args_list


def _inputchoice_calls(mock_ic):
    return mock_ic.call_args_list


class TestPromptOptionsContract:
    """Pins the ``options`` argument shape to ``io.inputchoice``."""

    def test_options_arg_is_tight_char_set(self):
        """The bug this test guards: ``options`` must be the literal
        character set ``"0123456789QR"``, not the human-readable label.

        If a future regression sneaks a label (or removes any character)
        back into ``PROMPT_OPTIONS``, ``inputchoice`` will reject real
        keystrokes and the door-mode loop will bell forever.
        """
        svc = _make_svc(move_returns=[{"type": "tictactoe_result", "board": [0] * 9, "winner": None, "is_draw": True, "moves_played": 0, "payout": 0, "winner_moniker": "?", "new_balance": 0}])
        with patch.object(tt_main.io, "inputchoice", return_value="5") as mock_ic, \
             patch.object(tt_main.io, "echo"):
            tt_main._run_mode1(svc, PLAYER)

        assert mock_ic.called, "io.inputchoice was not called"
        options = mock_ic.call_args.kwargs.get("options") \
            if mock_ic.call_args.kwargs else mock_ic.call_args.args[0]
        assert options == "0123456789QR", (
            f"PROMPT_OPTIONS passed to inputchoice must be the tight "
            f"char set '0123456789QR'; got {options!r}"
        )

    def test_prompt_includes_option_label(self):
        """The human-visible prompt self-documents the menu as
        ``[0-8] Q R``, matching the blackjack/yahtzee/slots convention
        of embedding the bracket label in the prompt and keeping the
        ``options`` arg compact.
        """
        svc = _make_svc(move_returns=[{"type": "tictactoe_result", "board": [0] * 9, "winner": None, "is_draw": True, "moves_played": 0, "payout": 0, "winner_moniker": "?", "new_balance": 0}])
        with patch.object(tt_main.io, "inputchoice", return_value="5") as mock_ic, \
             patch.object(tt_main.io, "echo"):
            tt_main._run_mode1(svc, PLAYER)

        prompt = mock_ic.call_args.kwargs.get("prompt") \
            if mock_ic.call_args.kwargs else mock_ic.call_args.args[1]
        assert "[0-8] Q R" in prompt, (
            f"prompt should self-document the menu as '[0-8] Q R'; "
            f"got {prompt!r}"
        )


class TestRunMode1Dispatch:
    """Each user keystroke must reach the right handler."""

    def test_digit_5_dispatches_to_play_move(self):
        """Regression: typing '5' must call ``svc.play_move(.., 5)``.

        Previously, '5' never reached ``play_move`` because
        ``inputchoice`` rejected it as not in the options set.
        """
        terminal = {"type": "tictactoe_result", "board": [0] * 9, "winner": None, "is_draw": True, "moves_played": 0, "payout": 0, "winner_moniker": "?", "new_balance": 0}
        svc = _make_svc(move_returns=[terminal])
        with patch.object(tt_main.io, "inputchoice", return_value="5") as mock_ic, \
             patch.object(tt_main.io, "echo"):
            tt_main._run_mode1(svc, PLAYER)

        assert svc.play_move.call_args.args == (TABLE_MONIKER, PLAYER, 5)
        assert svc.resign.called is False

    def test_digit_0_dispatches_to_play_move(self):
        terminal = {"type": "tictactoe_result", "board": [0] * 9, "winner": None, "is_draw": True, "moves_played": 0, "payout": 0, "winner_moniker": "?", "new_balance": 0}
        svc = _make_svc(move_returns=[terminal])
        with patch.object(tt_main.io, "inputchoice", return_value="0") as mock_ic, \
             patch.object(tt_main.io, "echo"):
            tt_main._run_mode1(svc, PLAYER)

        assert svc.play_move.call_args.args == (TABLE_MONIKER, PLAYER, 0)

    def test_uppercase_q_returns_zero_without_play_move(self):
        svc = _make_svc()
        with patch.object(tt_main.io, "inputchoice", return_value="Q") as mock_ic, \
             patch.object(tt_main.io, "echo") as mock_echo:
            rc = tt_main._run_mode1(svc, PLAYER)

        assert rc == 0
        assert svc.play_move.called is False
        assert svc.resign.called is False

    def test_uppercase_r_calls_resign_then_continues_loop(self):
        """R triggers ``svc.resign`` and the loop continues with the
        resign-result as the next state.
        """
        resign_state = {
            "type": "tictactoe_result",
            "table_moniker": TABLE_MONIKER,
            "mode": 1,
            "board": [0] * 9,
            "winner": 2,
            "is_draw": False,
            "is_over": True,
            "last_move": {"by": PLAYER, "resigned": True},
            "moves_played": 0,
            "winner_moniker": "AI_O",
            "payout": 0,
            "new_balance": 0,
        }
        svc = _make_svc(resign_returns=resign_state)
        with patch.object(tt_main.io, "inputchoice", return_value="R") as mock_ic, \
             patch.object(tt_main.io, "echo"):
            tt_main._run_mode1(svc, PLAYER)

        assert svc.resign.called
        assert svc.resign.call_args.args == (TABLE_MONIKER, PLAYER)
        assert svc.play_move.called is False

    def test_non_digit_response_emits_friendly_error(self):
        """If ``inputchoice`` somehow yields a non-digit, non-letter
        response (defensive; the upstream filter normally prevents this),
        the loop must surface the ``{level.error}`` hint and continue
        rather than crash on ``int()``.

        We bypass ``inputchoice`` by directly invoking it with a value
        outside its known set via a side_effect sequence.
        """
        svc = _make_svc()
        with patch.object(tt_main.io, "inputchoice", return_value="X") as mock_ic, \
             patch.object(tt_main.io, "echo") as mock_echo:
            # Patch inputchoice to deliver an illegal char first, then "5"
            # so the loop makes it to the play_move branch afterwards.
            mock_ic.side_effect = ["X", "5"]
            # Second play_move returns tictactoe_result to exit.
            svc.play_move.side_effect = [
                {"type": "tictactoe_result", "board": [0] * 9, "winner": None,
                 "is_draw": True, "moves_played": 0, "payout": 0,
                 "winner_moniker": "?", "new_balance": 0}
            ]
            tt_main._run_mode1(svc, PLAYER)

        # The friendly error message must have been emitted.
        echoed_texts = " ".join(
            str(c.args[0]) if c.args else "" for c in mock_echo.call_args_list
        )
        assert "enter a digit 0-8" in echoed_texts, (
            f"expected friendly error in echo calls; got: {echoed_texts!r}"
        )
        # After the error, play_move was eventually reached on a valid input.
        assert svc.play_move.called
