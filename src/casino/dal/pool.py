# casino/dal/pool.py
# The one way casino entry points obtain their connection pool.
#
# bbsengine6's getpool caches one pool per database, so every caller in a process shares it.
# Closing that shared pool when a `with` block ends would tear it down under the next caller
# and rebuild it. process_pool therefore yields the cached pool and leaves it open: the process
# owns it, and reset_pool_cache() is the single place it is closed.

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from bbsengine6 import database


@contextmanager
def process_pool(args: Any, **kwargs: Any) -> Iterator[Any]:
    """Yield the process's cached connection pool for ``args``'s database. Does not close it."""
    yield database.getpool(args, **kwargs)
