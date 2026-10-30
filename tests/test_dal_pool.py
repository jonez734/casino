"""casino.dal.pool.process_pool: one cached pool per process, never closed by a scope.

Covers:
  - the same pool is yielded to every scope for a database;
  - leaving a scope, normally or by an error, does not close the pool;
  - the pool is still usable after a scope has ended.
"""

from argparse import Namespace
from unittest.mock import MagicMock, patch

import pytest

from casino.dal import pool as casino_pool


pytestmark = pytest.mark.unit


def _args(name="zoid6test"):
    return Namespace(databasename=name, databasehost="h", databaseport=5432,
                     databaseuser="u", databasepassword=None, debug=False)


def test_scopes_share_one_pool():
    shared = MagicMock(name="pool")
    with patch.object(casino_pool.database, "getpool", return_value=shared) as getpool:
        with casino_pool.process_pool(_args()) as first:
            pass
        with casino_pool.process_pool(_args()) as second:
            pass
    assert first is shared
    assert second is shared
    assert getpool.call_count == 2  # asked each time; bbsengine6 returns the cached one


def test_leaving_a_scope_does_not_close_the_pool():
    pool = MagicMock(name="pool")
    with patch.object(casino_pool.database, "getpool", return_value=pool):
        with casino_pool.process_pool(_args()):
            pass
    pool.close.assert_not_called()
    pool.__exit__.assert_not_called()


def test_an_error_inside_the_scope_does_not_close_the_pool():
    pool = MagicMock(name="pool")
    with patch.object(casino_pool.database, "getpool", return_value=pool):
        with pytest.raises(RuntimeError):
            with casino_pool.process_pool(_args()):
                raise RuntimeError("boom")
    pool.close.assert_not_called()


def test_the_pool_is_usable_after_a_scope_ends():
    pool = MagicMock(name="pool")
    with patch.object(casino_pool.database, "getpool", return_value=pool):
        with casino_pool.process_pool(_args()):
            pass
        with casino_pool.process_pool(_args()) as again:
            assert again is pool
            again.connection()
    pool.close.assert_not_called()
    pool.connection.assert_called_once()


def test_the_database_name_is_passed_through():
    with patch.object(casino_pool.database, "getpool", return_value=MagicMock()) as getpool:
        with casino_pool.process_pool(_args("zoid6test"), database="zoid6test"):
            pass
    assert getpool.call_args.kwargs.get("database") == "zoid6test"
