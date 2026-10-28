# casino/tests/test_awaited_table_calls_use_async_pool.py
# The handler's awaited (aiosql) table calls must receive the async connection pool. Passing the
# sync pool context manager raises "can't be used in 'await' expression" at run time.

import re
from pathlib import Path

import casino

HANDLER = Path(casino.__file__).resolve().parent / "api" / "handler.py"


def test_awaited_table_calls_do_not_receive_the_sync_pool():
    text = HANDLER.read_text(encoding="utf-8")
    awaited = re.findall(r"await async_dal_table\.\w+\([^)]*pool=(self\._pool)", text)
    assert awaited == [], f"awaited table calls still pass the sync pool: {len(awaited)}"


def test_async_pool_resolver_is_used_for_awaited_calls():
    text = HANDLER.read_text(encoding="utf-8")
    assert "_resolve_async_pool" in text
    assert text.count("pool=await _resolve_async_pool(self.args)") >= 4
