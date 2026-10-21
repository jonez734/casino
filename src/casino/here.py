"""``@here`` for casino: the message group of the sender's current table.

bbsengine6 expands ``@here`` through a resolver the host registers. This module
is casino's resolver. A sender seated at a table (``player`` or ``dealer``)
resolves to that table's group, ``table:<moniker>``. A sender with no seat has
no location, so ``@here`` is refused rather than sent to nobody.
"""

from __future__ import annotations

from typing import Optional

from bbsengine6 import database, io
from bbsengine6.message import service as _msg

from casino import tablegroups

SEATED_ROLES = ("player", "dealer")


def current_table_moniker(args, moniker: str, *, conn=None) -> Optional[str]:
    """The table the member is seated at, or None."""
    if not moniker:
        return None
    try:
        with database.connect(args, conn=conn) as c, c.cursor() as cur:
            cur.execute(
                "SELECT cardtablemoniker FROM casino.map_cardtable_player "
                "WHERE playermoniker = %s AND role IN ('player', 'dealer') LIMIT 1",
                (moniker,),
            )
            row = cur.fetchone()
            return row[0] if row else None
    except Exception:
        io.echo_traceback("casino.here.current_table_moniker:")
        return None


_args = None


def resolve_here(sender_moniker: Optional[str]) -> Optional[str]:
    """Group name for ``@here`` for this sender, or None when not seated."""
    if _args is None:
        return None
    table = current_table_moniker(_args, sender_moniker)
    return tablegroups.table_group_name(table) if table else None


def install(args) -> None:
    """Register casino's ``@here`` resolver with bbsengine6, bound to ``args``."""
    global _args
    _args = args
    _msg.set_here_resolver(resolve_here)
