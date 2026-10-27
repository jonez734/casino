"""Bots: explicit, seated computer players (Phase 4, slice 3).

A bot is a real member with its own bank account, just like a human player. It has a casino
player marked ``attrs.is_bot = true`` and a seat at a table. Its member password is random and
never shown, so no one can log in as it.

Bots are clocked like humans (see the poker and round clocks). ``remove_bot`` unseats a bot and
keeps its member row and bank account, so the chips and history are never lost.
"""

from __future__ import annotations

import secrets
from typing import Any, Optional

from bbsengine6 import database, member

from casino import seats
from casino.dal import player as dal_player
from casino.dal import table as dal_table

BOT_PREFIX = "bot_"
BOT_EMAIL_DOMAIN = "bot.local"


def bot_moniker(table_moniker: str, index: int) -> str:
    """A moniker for a bot seated at ``table_moniker``.

    engine.__member accepts only letters, digits, and underscores (chk_member_moniker_format), so
    the table name is reduced to those characters and capped in length. The index keeps it unique
    within a table.
    """
    base = "".join(c if (c.isascii() and c.isalnum()) else "_" for c in table_moniker.lower())
    return f"{BOT_PREFIX}{base[:24]}_{index}"


def new_bot_password() -> str:
    """A random password that is never shown or stored anywhere readable."""
    return secrets.token_urlsafe(32)


def _set_password(args: Any, password: str, moniker: str, *, pool: Any = None) -> None:
    member.setpassword(args, password, moniker, pool=pool)


def _create_bot_member(args: Any, moniker: str, *, pool: Any = None) -> None:
    """Create the member row for a bot, approved, with a password nobody knows."""
    with database.connect(args, pool=pool) if pool is not None else database.connect(args) as conn, \
            database.cursor(conn) as cur:
        cur.execute(
            "INSERT INTO engine.__member (moniker, email, approved, loginid) "
            "VALUES (%s, %s, true, %s) ON CONFLICT (moniker) DO NOTHING",
            (moniker, f"{moniker}@{BOT_EMAIL_DOMAIN}", moniker),
        )
    _set_password(args, new_bot_password(), moniker, pool=pool)


def _table_seat_rule(args: Any, table_moniker: str, *, pool: Any = None):
    """The seat module for the table's game, or ``None`` when the table or its game has none."""
    table = dal_table.get_table(args, table_moniker, pool=pool)
    if not table:
        return None
    return seats.seat_module(table.get("type"))


def _moniker_taken(args: Any, moniker: str, *, pool: Any = None) -> bool:
    """True when a member already has this moniker, so a new bot must pick another."""
    with database.connect(args, pool=pool) if pool is not None else database.connect(args) as conn, \
            database.cursor(conn) as cur:
        cur.execute("SELECT 1 FROM engine.__member WHERE moniker = %s", (moniker,))
        return cur.fetchone() is not None


def _next_bot_moniker(args: Any, table_moniker: str, *, pool: Any = None) -> str:
    """The first bot moniker at this table that no member uses yet.

    The index is not the seat count: removing a bot frees its seat, but its member row stays, so
    the count can point back at a name that is still in use.
    """
    index = 1
    while True:
        name = bot_moniker(table_moniker, index)
        if not _moniker_taken(args, name, pool=pool):
            return name
        index += 1


def _open_bank_account(args: Any, moniker: str, *, pool: Any = None) -> None:
    """Open the bot's bank account, as a human player gets one."""
    with database.connect(args, pool=pool) if pool is not None else database.connect(args) as conn, \
            database.cursor(conn) as cur:
        cur.execute(
            "INSERT INTO bank.__account (moniker, balance) VALUES (%s, 0) ON CONFLICT (moniker) DO NOTHING",
            (moniker,),
        )


class BotService:
    """Adds and removes bots at a table. Capacity is the seat module's rule."""

    def __init__(self, args: Any, *, pool: Any = None):
        self.args = args
        self._pool = pool

    def add_bot(self, table_moniker: str) -> dict[str, Any]:
        """Seat one new bot at ``table_moniker``.

        The bot is a member with a bank account and a casino player marked as a bot. It is refused
        when the table has no free seat, and nothing is created in that case.
        """
        table = dal_table.get_table(self.args, table_moniker, pool=self._pool)
        if not table:
            return {"success": False, "message": "Table not found"}

        game_type = table.get("type")
        if seats.seat_module(game_type) is not None:
            taken = dal_table.count_seated(self.args, table_moniker, pool=self._pool)
            if not seats.has_room(game_type, taken):
                return {"success": False, "message": f"Table {table_moniker} is full ({taken} seated)"}
        else:
            taken = 0

        name = _next_bot_moniker(self.args, table_moniker, pool=self._pool)
        _create_bot_member(self.args, name, pool=self._pool)
        _open_bank_account(self.args, name, pool=self._pool)
        # The casino player row must exist before its attrs are set, or the UPDATE does nothing.
        dal_player.get_or_create_player(self.args, name)
        dal_player.set_player_attrs(self.args, name, {"is_bot": True}, pool=self._pool)
        dal_table.add_player_to_table(self.args, table_moniker, name, pool=self._pool)
        return {"success": True, "bot": name, "message": f"Bot {name} sat down at {table_moniker}"}

    def fill_bots(self, table_moniker: str, count: Optional[int] = None) -> dict[str, Any]:
        """Seat bots one at a time until ``count`` are added, or every empty seat is full.

        Each bot is added by :meth:`add_bot`, so each one follows the same rules. A table that is
        already full is not an error: the result lists the bots added, which may be none. A game
        with no seat rule has nothing to fill.
        """
        if count is not None and count < 0:
            return {"success": False, "message": "count cannot be negative", "added": []}
        if _table_seat_rule(self.args, table_moniker, pool=self._pool) is None:
            return {"success": True, "added": [], "message": "This game has no seats to fill"}

        added: list[str] = []
        while count is None or len(added) < count:
            result = self.add_bot(table_moniker)
            if not result.get("success"):
                break
            added.append(result["bot"])
        return {
            "success": True,
            "added": added,
            "message": f"Added {len(added)} bot(s) to {table_moniker}",
        }

    def remove_bot(self, table_moniker: str, bot_moniker_: str) -> dict[str, Any]:
        """Unseat a bot. Refused for a human seat. The bot's account and member row are kept."""
        attrs = dal_player.get_player_attrs(self.args, bot_moniker_, pool=self._pool)
        if not attrs.get("is_bot"):
            return {"success": False, "message": f"{bot_moniker_} is not a bot"}
        removed = dal_table.remove_player_from_table(
            self.args, table_moniker, bot_moniker_, pool=self._pool
        )
        return {
            "success": bool(removed),
            "message": f"Bot {bot_moniker_} left {table_moniker}" if removed else "Not at table",
        }
