#!/usr/bin/env python3
"""Tests for the width-aware, locale-aware client table renderer.

Covers ``casino.client.table_render._safe_int_str`` /
``_signed_str`` / ``render_table`` and the integration through
``CasinoClient.handle_message`` for ``table_list`` /
``bank_list_all``.

The locale tests pin two invariants:

1. ``_safe_int_str`` adds the locale's thousands separator when the
   separator is ASCII (``en_US``, ``C``), and
2. ``_safe_int_str`` falls back to a plain integer string when the
   separator is non-ASCII (regression guard for ``fr_FR``/NBSP).

The width tests pin that ``render_table`` uses
``io.terminal.width()`` as its budget, and that long cells in the last
column truncate with an ellipsis.

The ``handle_message`` tests verify that the rendered lines have equal
visible width and that locale-formatted numbers appear in the output.
"""

from __future__ import annotations

import argparse
import asyncio
import locale
import re
import sys
from unittest.mock import patch

sys.path.insert(0, "/home/opencode/data/work/casino/src")


def _strip_tags(line: str) -> str:
    """Remove bbsengine6 color tags and ANSI escapes for visible-width math."""
    def _expand(match: re.Match) -> str:
        body = match.group(1)
        if body.startswith("hline:"):
            try:
                count = int(body.split(":", 1)[1])
            except ValueError:
                return ""
            return "─" * count
        return ""

    hline_re = re.compile(r"\{(hline:\d+)\}")
    line = hline_re.sub(_expand, line)
    return re.sub(r"\{[^}]*\}+|\[[0-9;]*m", "", line)


def _make_args() -> argparse.Namespace:
    return argparse.Namespace(bed_host="127.0.0.1", bed_port=8765, bed_path="/")


def _make_client():
    from casino.client import CasinoClient

    return CasinoClient(_make_args())


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _reset_locale():
    """Restore locale to whatever was active when the test process started."""
    locale.setlocale(locale.LC_ALL, "C")


# ---- _safe_int_str / _signed_str ------------------------------------------


def test_safe_int_str_c_locale_no_separator():
    """``C`` locale omits the thousands separator."""
    from casino.client.table_render import _safe_int_str

    try:
        locale.setlocale(locale.LC_NUMERIC, "C")
        assert _safe_int_str(1234567) == "1234567"
        assert _safe_int_str(0) == "0"
        assert _safe_int_str(-42) == "-42"
    finally:
        _reset_locale()


def test_safe_int_str_en_us_locale_uses_comma():
    """``en_US.UTF-8`` inserts a comma every three digits."""
    from casino.client.table_render import _safe_int_str

    try:
        try:
            locale.setlocale(locale.LC_NUMERIC, "en_US.UTF-8")
        except locale.Error:
            try:
                locale.setlocale(locale.LC_NUMERIC, "en_US")
            except locale.Error:
                return  # locale not installed on the runner
        assert _safe_int_str(1234567) == "1,234,567"
        assert _safe_int_str(0) == "0"
    finally:
        _reset_locale()


def test_safe_int_str_falls_back_on_non_ascii_separator():
    """When the locale produces a non-ASCII separator, fall back to plain int.

    Regression guard: ``fr_FR`` uses NARROW NO-BREAK SPACE
    (``\\u202F``) as its thousands separator, which would skew the
    column-width math. ``_safe_int_str`` must detect that and emit the
    un-grouped form instead.
    """
    from casino.client.table_render import _safe_int_str

    try:
        try:
            locale.setlocale(locale.LC_NUMERIC, "fr_FR")
        except locale.Error:
            return  # locale not installed on the runner; nothing to test

        result = _safe_int_str(1234567)
        # fr_FR thousands sep is NBSP; the safe-path must NOT include it.
        assert "\xa0" not in result, (
            f"expected fallback to plain integer, got NBSP in {result!r}"
        )
        assert result == "1234567", f"expected '1234567', got {result!r}"
    finally:
        _reset_locale()


def test_signed_str_preserves_sign_and_grouping():
    """``_signed_str`` always renders an explicit ``+`` or ``-`` prefix."""
    from casino.client.table_render import _signed_str

    try:
        locale.setlocale(locale.LC_NUMERIC, "C")
        assert _signed_str(50) == "+50"
        assert _signed_str(-50) == "-50"
        assert _signed_str(0) == "+0"
    finally:
        _reset_locale()


# ---- render_table --------------------------------------------------------


def test_render_table_basic_alignment():
    """Each row's visible width equals the header rule's visible width."""
    from casino.client.table_render import render_table

    with patch("bbsengine6.io.terminal.width", return_value=40):
        rows = [
            ["blackjack-jam", "blackjack", "1,234", "9,999", "alice, bob"],
            ["poker-main", "poker", "20", "2,000", "(empty)"],
        ]
        out = render_table(
            ["Moniker", "Game", "Min", "Max", "Players"],
            rows,
            alignments=["l", "l", "r", "r", "l"],
        )
        widths = {len(_strip_tags(line)) for line in out}
        assert len(widths) == 1, f"expected uniform width, got {widths}"
        # Rule width + 2 (the leading/trailing space) should match the row width.
        rule_line = out[0]
        assert "{hline:" in rule_line
        # The row right-alignment for numerics must keep "20" with leading spaces.
        assert "   20" in out[-1] or "  20" in out[-1]


def test_render_table_truncates_with_ellipsis():
    """Long cells in a narrow terminal end with the configured ellipsis."""
    from casino.client.table_render import render_table

    with patch("bbsengine6.io.terminal.width", return_value=30):
        rows = [
            [
                "blackjack-jam",
                "blackjack",
                "1",
                "9",
                "alice, bob, charlie, dave, eve, frank",
            ]
        ]
        out = render_table(
            ["Moniker", "Game", "Min", "Max", "Players"],
            rows,
            alignments=["l", "l", "r", "r", "l"],
        )
        player_cell = out[-1]
        assert "…" in player_cell, f"expected ellipsis in {player_cell!r}"


def test_render_table_alignments_must_match_headers():
    """Misaligned ``alignments`` argument raises ``ValueError``."""
    from casino.client.table_render import render_table

    try:
        render_table(["A", "B"], [["1", "2"]], alignments=["l"])
    except ValueError:
        return
    raise AssertionError("expected ValueError for mismatched alignments")


# ---- handle_message integration ------------------------------------------


def test_handle_message_table_list_renders_locale_number():
    """The ``table_list`` branch emits a header rule + row per table.

    Numeric cells carry the locale-formatted thousands separator under
    the en_US locale (or the plain integer under C).
    """
    client = _make_client()
    payload = {
        "type": "table_list",
        "tables": [
            {
                "moniker": "blackjack-jam",
                "game_type": "blackjack",
                "min_bet": 1234567,
                "max_bet": 9999999,
                "players": ["alice", "bob"],
            },
            {
                "moniker": "poker-main",
                "game_type": "poker",
                "min_bet": 50,
                "max_bet": 5000,
                "players": [],
            },
        ],
    }

    try:
        try:
            locale.setlocale(locale.LC_NUMERIC, "en_US.UTF-8")
        except locale.Error:
            try:
                locale.setlocale(locale.LC_NUMERIC, "en_US")
            except locale.Error:
                locale.setlocale(locale.LC_NUMERIC, "C")
        with patch("bbsengine6.io.terminal.width", return_value=80), \
             patch("casino.client.casino_client.io.echo") as mock_echo, \
             patch("casino.client.casino_client.util.hr"):
            _run(client.handle_message(payload))
            lines = [call.args[0] for call in mock_echo.call_args_list]
            joined = " ".join(lines)
            expected_sep = locale.format_string("%d", 1234567, grouping=True)
    finally:
        _reset_locale()

    assert mock_echo.call_count >= 4
    visible_widths = {len(_strip_tags(call.args[0])) for call in mock_echo.call_args_list}
    assert len(visible_widths) == 1, f"expected uniform width, got {visible_widths}"
    if "," in expected_sep:
        assert "1,234,567" in joined, (
            f"expected en_US-formatted number in rendered output; got: {joined!r}"
        )
    else:
        assert "1234567" in joined


def test_handle_message_bank_list_all_renders_locale_number():
    """The ``bank_list_all`` branch picks up the locale too."""
    client = _make_client()
    payload = {
        "type": "bank_list_all",
        "tables": [
            {
                "moniker": "blackjack-jam",
                "owner": "alice",
                "bank": 1000000,
                "max_transfer": 500000,
                "type": "blackjack",
            }
        ],
    }

    try:
        try:
            locale.setlocale(locale.LC_NUMERIC, "en_US.UTF-8")
        except locale.Error:
            try:
                locale.setlocale(locale.LC_NUMERIC, "en_US")
            except locale.Error:
                locale.setlocale(locale.LC_NUMERIC, "C")
        with patch("bbsengine6.io.terminal.width", return_value=80), \
             patch("casino.client.casino_client.io.echo") as mock_echo, \
             patch("casino.client.casino_client.util.hr"):
            _run(client.handle_message(payload))
            lines = [call.args[0] for call in mock_echo.call_args_list]
            joined = " ".join(lines)
            expected_sep = locale.format_string("%d", 1000000, grouping=True)
    finally:
        _reset_locale()
    if "," in expected_sep:
        assert "1,000,000" in joined, (
            f"expected en_US-formatted bank; got: {joined!r}"
        )
    else:
        assert "1000000" in joined


def test_handle_message_empty_table_list_says_no_tables():
    """Empty ``table_list`` payload prints the legacy message and no rule."""
    client = _make_client()
    with patch("bbsengine6.io.terminal.width", return_value=80), \
         patch("casino.client.casino_client.io.echo") as mock_echo, \
         patch("casino.client.casino_client.util.hr"):
        _run(client.handle_message({"type": "table_list", "tables": []}))

    assert mock_echo.call_count == 1
    assert mock_echo.call_args.args[0] == "No tables available."
