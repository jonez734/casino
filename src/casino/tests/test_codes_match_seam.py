"""Casino's shared result codes come from bbsengine6's seam vocabulary, and their wire values do not change.

The generic codes (handbook/specs/front-end-seam.md, section 4) have one definition, in
bbsengine6.seam.codes. A casino code that duplicates a generic code is imported from there, so the
two cannot drift. Casino-specific codes stay in casino.
"""

import importlib

import pytest

from bbsengine6.seam.codes import ErrorCode as Generic

auth = importlib.import_module("casino.api._auth")
messages = importlib.import_module("casino.api.messages")

pytestmark = pytest.mark.unit

# casino's generic codes and the names they had before the move. The value must not change.
SHARED = {
    "CODE_NOT_AUTHENTICATED": "not_authenticated",
    "CODE_FORBIDDEN": "forbidden",
    "CODE_NOT_AT_TABLE": "not_at_table",
    "CODE_INVALID_AMOUNT": "invalid_amount",
}


@pytest.mark.parametrize("name,value", sorted(SHARED.items()))
def test_wire_value_is_unchanged(name, value):
    assert getattr(auth, name) == value


def test_shared_generic_codes_are_the_seam_values():
    for name, value in {
        "CODE_NOT_AUTHENTICATED": "not_authenticated",
        "CODE_FORBIDDEN": "forbidden",
    }.items():
        assert value in {c.value for c in Generic}, name


def test_table_and_money_codes_are_casino_not_seam():
    # not_at_table, table_not_found, invalid_bet and insufficient_funds are casino's own codes.
    seam = {c.value for c in Generic}
    for value in ("not_at_table", "table_not_found", "invalid_bet", "insufficient_funds"):
        assert value not in seam, value


def test_messages_error_codes_are_seam_codes_where_they_overlap():
    seam = {c.value for c in Generic}
    for m in messages.ErrorCode:
        if m.value in seam:
            assert m.value == Generic(m.value).value


def test_casino_specific_codes_stay_in_casino():
    # bot_refused and friends are casino's own refusals; they are not in the generic set.
    assert "bot_refused" not in {c.value for c in Generic}


def test_handler_has_no_literal_shared_codes():
    # The handler's responses use the seam's values by name, not as repeated string literals, so a
    # rename in the seam cannot leave a stale copy behind in the handler.
    import pathlib
    import re

    src = pathlib.Path(importlib.import_module("casino.api.handler").__file__).read_text(encoding="utf-8")
    seam = {c.value for c in Generic if c.value != "ok"}
    for value in seam:
        assert not re.search(r'"code":\s*"' + re.escape(value) + '"', src), value
