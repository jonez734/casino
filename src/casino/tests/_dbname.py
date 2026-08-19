"""Resolve the casino test database name.

Resolution order (first wins):
  1. ``pytest --databasename=NAME`` (registered by conftest.py)
  2. ``BBSENGINE6_DBNAME`` environment variable
  3. Default ``"zoid6"``

The active value is set by ``casino.tests.conftest.pytest_configure``
once pytest has parsed ``--databasename``. unittest-based tests
(which can't take fixtures) import ``current_dbname()`` /
``dbname_args()`` from here.

Not a ``test_*.py`` filename so pytest's collector ignores it.
"""
from __future__ import annotations

import os

DEFAULT_DBNAME = "zoid6"
DBNAME_ENV = "BBSENGINE6_DBNAME"


_active_dbname: list[str] = [os.environ.get(DBNAME_ENV, DEFAULT_DBNAME)]


def set_active_dbname(name: str) -> None:
    """Called by conftest.py once ``--databasename`` is resolved."""
    _active_dbname[0] = name


def current_dbname() -> str:
    """Return the resolved database name for casino tests."""
    return _active_dbname[0]


def dbname_args() -> list[str]:
    """Argparse argv list for ``parser.parse_args(...)`` callers."""
    return ["--databasename", _active_dbname[0]]
