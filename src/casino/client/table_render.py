# casino/client/table_render.py
# Width-aware, locale-aware table rendering for the WS casino client.
#
# All tabular output in casino_client.handle_message previously hardcoded
# column widths and ignored io.terminal.width(). This module centralises
# the layout so every screen uses the available terminal width, supports
# trailing-column ellipsis truncation, and formats numeric cells with the
# user's locale (via the ``n`` format spec) without breaking alignment on
# terminals whose locale uses a non-ASCII group separator.

from __future__ import annotations

import re
from collections.abc import Sequence

from bbsengine6 import io, util

_LABEL_OPEN = "{var:labelcolor}"
_LABEL_CLOSE = "{/all}"
_VALUE_OPEN = "{var:valuecolor}"
_VALUE_CLOSE = "{/all}"
_RULE_OPEN = "{boxcolor}"
_RULE_CLOSE = "{/all}"

_OUTER_PAD = 2
_MIN_COL_WIDTH = 4

_ASCII_SAFE_INT = re.compile(r"^[0-9+\-,.]+$")


def _safe_int_str(n: int | float) -> str:
    """Format an integer using the active locale, falling back on non-ASCII output.

    Uses the ``n`` format spec so en_US yields ``1,234,567`` and ``C`` yields
    ``1234567``. If the resulting string contains any character outside the
    ASCII digits / sign set, the locale separator is non-ASCII (e.g. NBSP in
    fr_FR, narrow-NBSP in some de_DE variants), which would skew the column
    width math. In that case fall back to a plain ``str(int(n))`` so the
    rendered line stays aligned even at the cost of dropping the grouping.
    """
    formatted = f"{int(n):n}"
    if _ASCII_SAFE_INT.match(formatted):
        return formatted
    return f"{int(n)}"


def _signed_str(n: int | float) -> str:
    """Locale-formatted integer with an explicit sign (``+`` / ``-``).

    The slot-history "net" column has historically used the ``:+d`` format
    spec to keep the sign visible. The plain ``n`` specifier collapses the
    sign, so build the string manually and re-validate that the locale
    group separator is still ASCII-safe.
    """
    value = int(n)
    sign = "+" if value >= 0 else "-"
    magnitude = abs(value)
    formatted = f"{magnitude:n}"
    if not _ASCII_SAFE_INT.match(formatted):
        formatted = str(magnitude)
    return f"{sign}{formatted}"


def _display_width(s: str) -> int:
    """Visible character width of ``s`` with bbsengine6 color tags stripped."""
    return len(util.strip_ansi(s))


def _truncate(value: str, width: int, ellipsis: str) -> str:
    if width <= 0:
        return ""
    if len(value) <= width:
        return value
    if width == 1:
        return ellipsis[0]
    return value[: width - 1] + ellipsis[0]


def _column_widths(
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    alignments: Sequence[str],
    available: int,
    min_col_width: int,
    ellipsis: str,
) -> list[int]:
    """Allocate per-column widths so the row total fits within ``available``.

    Variable-width columns (those whose natural width exceeds their requested
    share) are pushed down to the requested share and marked truncatable in
    the caller; the truncation happens at render time. Fixed columns claim
    their natural width.
    """
    n_cols = len(headers)
    if n_cols == 0:
        return []

    natural = [0] * n_cols
    for i, h in enumerate(headers):
        natural[i] = max(natural[i], len(h))
    for row in rows:
        for i, cell in enumerate(row):
            if i < n_cols:
                natural[i] = max(natural[i], len(str(cell)))

    widths = [max(min_col_width, w) for w in natural]
    overflow = sum(widths) - available
    if overflow <= 0:
        return widths

    reducible = [i for i in range(n_cols) if widths[i] > min_col_width]
    if not reducible:
        return widths

    while overflow > 0 and reducible:
        share = (overflow + len(reducible) - 1) // len(reducible)
        progressed = False
        for i in reducible:
            if overflow <= 0:
                break
            can_give = widths[i] - min_col_width
            if can_give <= 0:
                continue
            give = min(share, can_give, overflow)
            widths[i] -= give
            overflow -= give
            progressed = True
        if not progressed:
            break

    if overflow > 0:
        reducible = list(range(n_cols))
        for i in reducible:
            if overflow <= 0:
                break
            give = min(overflow, widths[i] - 1) if widths[i] > 1 else 0
            widths[i] -= give
            overflow -= give

    return widths


def _format_cell(value: str, width: int, align: str, ellipsis: str) -> str:
    text = _truncate(value, width, ellipsis)
    if align == "r":
        return text.rjust(width)
    return text.ljust(width)


def _rule(width: int) -> str:
    if width <= 0:
        return ""
    return f"{_RULE_OPEN}{{{f'hline:{width}'}}}{_RULE_CLOSE}"


def render_table(
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    *,
    alignments: Sequence[str] | None = None,
    min_col_width: int = _MIN_COL_WIDTH,
    ellipsis: str = "…",
    outer_pad: int = _OUTER_PAD,
) -> list[str]:
    """Render a tabular block sized to the current terminal width.

    Args:
        headers: Column header strings. Use title case to match the rest of
            the client.
        rows: One list per data row; each inner list must have one cell per
            column header. Cells are coerced to ``str`` for measurement but
            their content is preserved verbatim.
        alignments: Per-column alignment, ``"l"`` (default) or ``"r"``.
            Right-align numeric columns.
        min_col_width: Floor on every column width to keep headers readable.
        ellipsis: Trailing character used when truncating a long cell.
        outer_pad: Columns combined shrink to ``io.terminal.width() -
            outer_pad`` so the rule + cells don't kiss the terminal edge.

    Returns:
        A list of pre-formatted strings: rule, header, rule, then one line
        per input row. Each string carries bbsengine6 color tags and is
        intended to be passed to ``io.echo`` one-per-call (so the echo
        pipeline appends ``ECHO_END`` per line, per AGENTS.md).
    """
    if not headers:
        return []

    n_cols = len(headers)
    aligns = list(alignments) if alignments else ["l"] * n_cols
    if len(aligns) != n_cols:
        raise ValueError(
            f"alignments length ({len(aligns)}) must match headers ({n_cols})"
        )

    try:
        available = max(n_cols * min_col_width, io.terminal.width() - outer_pad)
    except (OSError, ValueError):
        available = max(n_cols * min_col_width, 100 - outer_pad)

    string_rows = [[str(c) for c in row] for row in rows]
    widths = _column_widths(
        headers, string_rows, aligns, available, min_col_width, ellipsis
    )

    def _row(values: Sequence[str], *, header: bool) -> str:
        parts: list[str] = []
        for i, val in enumerate(values):
            text = _truncate(str(val), widths[i], ellipsis)
            if header:
                open_tag, close_tag = _LABEL_OPEN, _LABEL_CLOSE
            else:
                open_tag, close_tag = _VALUE_OPEN, _VALUE_CLOSE
            if aligns[i] == "r":
                cell = f"{open_tag}{text.rjust(widths[i])}{close_tag}"
            else:
                cell = f"{open_tag}{text.ljust(widths[i])}{close_tag}"
            parts.append(cell)
        return " ".join(parts)

    rule = _rule(sum(widths) + (n_cols - 1))
    header_line = _row(headers, header=True)
    out: list[str] = []
    if rule:
        out.append(rule)
    out.append(header_line)
    if rule:
        out.append(rule)
    for row in string_rows:
        out.append(_row(row, header=False))
    return out
