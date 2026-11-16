"""A stake moved to a table lands in the bank account the table is mapped to (casino.__bank_table), not an account
named after the table. The table's moniker is not a bank account; the owner's account is.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from casino.dal import bet as dal_bet


pytestmark = pytest.mark.unit


def test_a_table_side_is_resolved_to_its_mapped_bank_account(monkeypatch):
    seen = []
    cur = MagicMock()

    def execute(q, params=None):
        seen.append(str(q))

    cur.execute.side_effect = execute
    cur.fetchone.return_value = {"id": 1}
    monkeypatch.setattr(dal_bet, "_resolve_bank_moniker", lambda args, name, pool=None: "jam" if name == "blackjack-jam" else name)
    monkeypatch.setattr(dal_bet, "_connect_ctx", _ctx(cur, monkeypatch))
    dal_bet._bank_move(SimpleNamespace(), "alice", "blackjack-jam", 10, "bet")
    assert any("'jam'" in q or "jam" in q for q in seen if "balance + " in q)


def _ctx(cur, monkeypatch):
    from bbsengine6 import database

    class _Conn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class _C:
        def __enter__(self):
            return cur

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(database, "cursor", lambda conn: _C())
    return lambda *a, **k: _Conn()
