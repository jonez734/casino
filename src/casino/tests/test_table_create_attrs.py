#!/usr/bin/env python3
# casino/tests/test_table_create_attrs.py
# create_table must store the table rules it is given (attrs, e.g. surrender) on the table row.
# Before this, the INSERT never wrote attrs, so every table kept the default rules. Stubbed: a fake
# cursor records the INSERT parameters, so no database is needed.

import json
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from casino.dal import table as dal_table


class _Cursor:
    def __init__(self):
        self.calls = []
        self._rows = []

    def execute(self, query, params=None):
        sql, kwargs = query if isinstance(query, tuple) else (str(query), params)
        self.calls.append((str(sql), kwargs))
        text = str(sql)
        if "FROM engine.__member" in text:
            self._rows = [{"moniker": "x"}]
        elif "FROM $casino.__table" in text or "FROM bank.__account" in text:
            self._rows = []
        elif "RETURNING id" in text:
            self._rows = [{"id": 1}]
        elif "INSERT INTO $casino.__table" in text:
            self._rows = [{
                "moniker": "blackjack-x", "type": "blackjack", "minimumbet": 10,
                "maximumbet": 1000, "ownermoniker": "x", "ownersince": None,
                "accountid": 1, "cheat": False, "cheatpercent": None, "attrs": {},
                "shoe_cards": None, "shoe_uses": 0, "location": "loc", "status": "open",
                "hidden": False,
            }]
        else:
            self._rows = [{"moniker": "x"}]

    def fetchone(self):
        if self._rows:
            return self._rows.pop(0)
        return None


def _run_create(attrs):
    cursor = _Cursor()

    @contextmanager
    def fake_connect(args, pool=None):
        conn = MagicMock()
        yield conn

    @contextmanager
    def fake_cursor(conn):
        yield cursor

    with patch.object(dal_table, "_connect_ctx", fake_connect), \
         patch.object(dal_table.database, "cursor", fake_cursor), \
         patch.object(dal_table.database, "query", side_effect=lambda sql, **kw: (sql, kw)), \
         patch.object(dal_table, "generate_table_name", return_value="loc"):
        dal_table.create_table(None, "blackjack", "x", 10, 1000, "blackjack-x", attrs=attrs)
    inserts = [p for q, p in cursor.calls if "INSERT INTO $casino.__table" in q]
    assert inserts, "create_table did not insert a table row"
    return inserts[0]


@pytest.mark.unit
def test_create_table_writes_the_rules_it_is_given():
    params = _run_create({"surrender": False, "shoe_decks": 6})
    assert json.loads(params["attrs"]) == {"surrender": False, "shoe_decks": 6}


@pytest.mark.unit
def test_create_table_without_attrs_stores_an_empty_object():
    params = _run_create(None)
    assert json.loads(params["attrs"]) == {}


@pytest.mark.unit
def test_handler_forwards_attrs_from_the_create_message():
    import inspect
    from casino.api import handler as h

    src = inspect.getsource(h)
    assert 'message.get("attrs")' in src
    assert "attrs=attrs" in src
