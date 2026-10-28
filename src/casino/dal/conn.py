# casino/dal/conn.py
# The one way casino opens database connections.
#
# bed runs each authenticated request under that member's database role (SET LOCAL ROLE
# <moniker>, see bed/main.py role_for_session). Casino's writes are gated by casino's own access
# rules, not by per-member database grants, so casino's connections keep the login role (bed) and
# ignore the request's role. This is what set_role=False does in bbsengine6.database.connect.

from __future__ import annotations

from typing import Any

from bbsengine6 import database


def connect(args: Any, pool: Any = None, **kwargs: Any):
    """A casino connection that runs as the login role, not the member role."""
    kwargs.setdefault("set_role", False)
    if pool is None:
        return database.connect(args, **kwargs)
    return database.connect(args, pool=pool, **kwargs)
