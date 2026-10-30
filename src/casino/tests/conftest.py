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
            "Falls back to env var BBSENGINE6_DBNAME, then default 'zoid6test'."
        ),
    )


def pytest_configure(config):
    cli = config.getoption("--databasename")
    env = os.environ.get(_dbname.DBNAME_ENV)
    _dbname.set_active_dbname(cli or env or _dbname.DEFAULT_DBNAME)


def pytest_sessionfinish(session, exitstatus):
    """Close the process's cached connection pools once, after the last test.

    bbsengine6 caches one pool per database, so every test shares it. Nothing else owns its end
    of life, and a pool whose worker threads are still running at interpreter exit crashes the
    shutdown. The session is the owner: it closes the cache here, before the interpreter exits.
    """
    from bbsengine6 import database

    database.reset_pool_cache()


@pytest.fixture
def dbname() -> str:
    """Resolved --databasename value as a pytest fixture."""
    return _dbname.current_dbname()


@pytest.fixture
def dbname_args() -> list[str]:
    """Argparse argv list for ``parser.parse_args(...)`` callers."""
    return _dbname.dbname_args()


@pytest.fixture(autouse=True)
def _no_table_group_writes(request, monkeypatch):
    """Keep table message-group side effects out of database-touching tests.

    Table create, seat, unseat, and delete write message groups through
    bbsengine6, on connections the tests do not roll back, so an unrelated test
    that touches a table could leave group rows in the live database. Replace
    the tablegroups entry points with no-op recorders for every test. Tests that
    exercise the group logic itself (test_tablegroups*) stub at a lower level
    and opt out with the ``tablegroups_real`` marker.
    """
    if request.node.get_closest_marker("tablegroups_real") is not None:
        yield
        return

    from casino import tablegroups as tg

    calls: list[tuple] = []

    def _recorder(name):
        def _record(*args, **kwargs):
            calls.append((name, args, kwargs))
        return _record

    for name in ("on_table_created", "on_seat", "on_unseat", "on_table_deleted"):
        monkeypatch.setattr(tg, name, _recorder(name))
    yield calls
