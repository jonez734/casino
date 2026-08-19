"""pytest plugin for casino tests.

Registers ``--databasename`` (default: env var ``BBSENGINE6_DBNAME``,
fallback: ``"zoid6"``). Resolution happens at ``pytest_configure``
time so unittest classes that build args inside ``setUp`` can read
the same value via ``casino.tests._dbname``.

The conftest file is at ``src/casino/tests/conftest.py``. We add
its directory to ``sys.path`` so ``import _dbname`` works regardless
of pytest's conftest-loading mode.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))
import _dbname  # noqa: E402


def pytest_addoption(parser, pluginmanager):
    group = parser.getgroup("casino")
    group.addoption(
        "--databasename",
        action="store",
        dest="databasename",
        default=None,
        help=(
            "PostgreSQL database name for casino tests. "
            "Falls back to env var BBSENGINE6_DBNAME, then default 'zoid6'."
        ),
    )


def pytest_configure(config):
    cli = config.getoption("--databasename")
    env = os.environ.get(_dbname.DBNAME_ENV)
    _dbname.set_active_dbname(cli or env or _dbname.DEFAULT_DBNAME)


@pytest.fixture
def dbname() -> str:
    """Resolved --databasename value as a pytest fixture."""
    return _dbname.current_dbname()


@pytest.fixture
def dbname_args() -> list[str]:
    """Argparse argv list for ``parser.parse_args(...)`` callers."""
    return _dbname.dbname_args()
