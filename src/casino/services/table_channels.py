# casino/services/table_channels.py
# The two channels every casino table has, built on bbsengine6's channel API.
#
#   <table_channel>:events   announce-only game events (poker and blackjack results and state,
#                            tictactoe and yahtzee events). Published by the server only.
#                            Subscribers: seated players, bots (through the announcer list),
#                            spectators, and sysop.
#   <table_channel>:chat     table chat. Publishing needs a subscription. Subscribers: seated
#                            players, spectators, and sysop.
#
# bbsengine6 owns channel records, subscriptions, the subscribe gate, and publishing. This module
# only supplies the casino rules: which monikers belong to a table (seated or watching), and the
# names. Seated players are read from casino.map_cardtable_player, so the same answer decides who
# may subscribe and who may announce.

from __future__ import annotations

from typing import Any, Optional

from bbsengine6.channel.naming import table_channel as _base_channel
from bbsengine6.net import channel_subscribe, channel_unsubscribe
from bbsengine6.services.channel import (
    ChannelService,
    register_subscribe_authority,
)

from casino.dal import table as dal_table

APP = "casino"
EVENTS = "events"
CHAT = "chat"

_authority_registered = False
_session_monikers: Any = None  # set by the router: callable(session_id) -> moniker


def events_channel(table_moniker: str) -> str:
    """The announce-only events channel for a table."""
    return f"{_base_channel(APP, table_moniker)}:{EVENTS}"


def chat_channel(table_moniker: str) -> str:
    """The chat channel for a table."""
    return f"{_base_channel(APP, table_moniker)}:{CHAT}"


def table_channels(table_moniker: str) -> tuple[str, str]:
    """Both channels of a table, events first."""
    return events_channel(table_moniker), chat_channel(table_moniker)


def table_moniker_of(channel_name: str) -> Optional[str]:
    """The table a casino table channel belongs to, or None for any other channel."""
    prefix = f"{_base_channel(APP, '')}"  # "casino:table:"
    if not channel_name.startswith(prefix):
        return None
    rest = channel_name[len(prefix):]
    for suffix in (f":{EVENTS}", f":{CHAT}"):
        if rest.endswith(suffix):
            return rest[: -len(suffix)] or None
    return None


def create_table_channels(args: Any, table_moniker: str, *, owner: str) -> dict[str, Any]:
    """Create the events and chat channels for a table. Idempotent: an existing channel is kept.

    The events channel is announce-only; its announcers are kept in step with the seats by
    sync_announcers. The chat channel is subscribe-restricted and needs a subscription to publish.
    """
    svc = ChannelService(args)
    events, chat = table_channels(table_moniker)
    results = {}
    for name, flags in (
        (events, {"announce_only": True}),
        (chat, {"subscribe_restricted": True, "publish_requires_subscription": True}),
    ):
        if svc.get_channel(name) is not None:
            results[name] = {"success": True, "existed": True}
            continue
        results[name] = svc.create_channel(
            name=name,
            createdby=owner,
            description=f"Table {table_moniker}",
            **flags,
        )
    return results


def sync_announcers(args: Any, table_moniker: str, *, owner: str) -> dict[str, Any]:
    """Make the events channel's announcers the table's seated monikers (players and bots).

    Uses bbsengine6's announcer API. ``owner`` (the table's creator, or sysop) is the actor that
    authorizes the change. Returns the moniker changes that failed, so callers can see them.
    """
    svc = ChannelService(args)
    events = events_channel(table_moniker)
    channel = svc.get_channel(events)
    if channel is None:
        return {"success": False, "message": "events channel not found"}
    current = set(channel.get("announcers") or [])
    wanted = set(dal_table.seated_monikers(args, table_moniker))
    failed: dict[str, str] = {}
    for moniker in sorted(wanted - current):
        res = svc.add_announcer(events, moniker, owner)
        if not res.get("success"):
            failed[moniker] = res.get("message", "")
    for moniker in sorted(current - wanted):
        res = svc.remove_announcer(events, moniker, owner)
        if not res.get("success"):
            failed[moniker] = res.get("message", "")
    return {"success": not failed, "failed": failed}


def subscribe_seat(channel_state: Any, session_id: int, table_moniker: str) -> None:
    """Subscribe a seated (or watching) session to both of a table's channels."""
    for name in table_channels(table_moniker):
        channel_subscribe(channel_state, session_id, name)


def unsubscribe_table(channel_state: Any, session_id: int, table_moniker: str) -> None:
    """Unsubscribe a session from both of a table's channels (leave or stop watching)."""
    for name in table_channels(table_moniker):
        channel_unsubscribe(channel_state, session_id, name)


def _authority(channel_name: str, moniker: str) -> Optional[bool]:
    """The casino subscribe rule for table channels.

    Returns None for channels that are not casino table channels, so other applications' rules
    are not overridden. For a table channel: a seated player or bot is allowed to both channels;
    a spectator is allowed to both channels (chat is open to spectators, events are for everyone
    at the table). Anyone else is refused.
    """
    table = table_moniker_of(channel_name)
    if table is None:
        return None
    if moniker in seated_at(table):
        return True
    if _is_watching(table, moniker):
        return True
    return False


def seated_at(table_moniker: str) -> list[str]:
    """Everyone seated at a table, from the store that owns its seats.

    Poker seats live in the poker service (in memory, persisted per table), so a poker table is
    asked there. A cash table's seats are in casino.map_cardtable_player.
    """
    args = _require_args()
    if _table_type(args, table_moniker) == "poker":
        from casino.services.poker import PokerService

        return PokerService(args).seated_monikers(table_moniker)
    return dal_table.seated_monikers(args, table_moniker)


def _table_type(args: Any, table_moniker: str) -> Optional[str]:
    from casino.dal import table as _dal

    row = _dal.get_table(args, table_moniker) or {}
    return row.get("type")


_registered_args: Any = None


def _require_args() -> Any:
    if _registered_args is None:
        raise RuntimeError("table channel authority used before register_table_channels(args)")
    return _registered_args


def _is_watching(table_moniker: str, moniker: str) -> bool:
    """True when a live session for ``moniker`` is spectating ``table_moniker``."""
    if _session_monikers is None:
        return False
    return bool(_session_monikers(table_moniker, moniker))


def register_table_channels(args: Any, *, session_is_watching: Any = None) -> None:
    """Install the casino subscribe rule. Call once at router start.

    ``session_is_watching(table_moniker, moniker) -> bool`` answers whether a live session for the
    moniker is spectating the table. The router supplies it from its session store.
    """
    global _authority_registered, _registered_args, _session_monikers
    _registered_args = args
    _session_monikers = session_is_watching
    if not _authority_registered:
        register_subscribe_authority(_authority)
        _authority_registered = True
