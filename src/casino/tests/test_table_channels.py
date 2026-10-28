# casino/tests/test_table_channels.py
# Table channels: each table has an events channel (announce-only) and a chat channel. Only seated
# players and bots (through the seat list) and spectators may subscribe; sysop may subscribe to
# anything. Spectators may read events and chat.
#
# Unit tests use the rule functions with the seat list and watcher lookup stubbed. Integration
# tests need the bbsengine6 channel migration applied to zoid6test and skip until it is.

from __future__ import annotations

import argparse
import uuid
from unittest.mock import patch

import pytest

from bbsengine6.net import ChannelState, channel_get_subscribers
from bbsengine6.services import channel as channel_module
from casino.services import table_channels as tc

ARGS = argparse.Namespace(databasename="zoid6test", debug=False)


def _moniker() -> str:
    return f"tc-{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------- naming (unit)


@pytest.mark.unit
def test_channel_names_are_namespaced_under_the_table():
    assert tc.events_channel("t1") == "casino:table:t1:events"
    assert tc.chat_channel("t1") == "casino:table:t1:chat"


@pytest.mark.unit
def test_a_table_channel_parses_back_to_its_table():
    assert tc.table_moniker_of("casino:table:t1:events") == "t1"
    assert tc.table_moniker_of("casino:table:t1:chat") == "t1"


@pytest.mark.unit
def test_non_table_channels_are_not_claimed():
    assert tc.table_moniker_of("system:shout") is None
    assert tc.table_moniker_of("casino:global") is None
    assert tc.table_moniker_of("member:alice") is None


@pytest.mark.unit
def test_a_table_moniker_containing_a_colon_suffix_is_kept_intact():
    assert tc.table_moniker_of("casino:table:odd:events:events") == "odd:events"


# ---------------------------------------------------------------- subscribe rule (unit)


@pytest.mark.unit
def test_seated_player_may_subscribe_to_both_channels():
    with patch.object(tc.dal_table, "seated_monikers", return_value=["alice"]), \
         patch.object(tc, "_require_args", return_value=ARGS), \
         patch.object(tc, "_session_monikers", return_value=False):
        assert tc._authority("casino:table:t1:events", "alice") is True
        assert tc._authority("casino:table:t1:chat", "alice") is True


@pytest.mark.unit
def test_bot_seat_may_subscribe():
    with patch.object(tc.dal_table, "seated_monikers", return_value=["casino-bot-1"]), \
         patch.object(tc, "_require_args", return_value=ARGS):
        assert tc._authority("casino:table:t1:events", "casino-bot-1") is True


@pytest.mark.unit
def test_spectator_may_subscribe_to_events_and_chat():
    with patch.object(tc.dal_table, "seated_monikers", return_value=[]), \
         patch.object(tc, "_require_args", return_value=ARGS), \
         patch.object(tc, "_session_monikers", return_value=True):
        assert tc._authority("casino:table:t1:events", "watcher") is True
        assert tc._authority("casino:table:t1:chat", "watcher") is True


@pytest.mark.unit
def test_outsider_may_not_subscribe():
    with patch.object(tc.dal_table, "seated_monikers", return_value=["alice"]), \
         patch.object(tc, "_require_args", return_value=ARGS), \
         patch.object(tc, "_session_monikers", return_value=False):
        assert tc._authority("casino:table:t1:events", "mallory") is False
        assert tc._authority("casino:table:t1:chat", "mallory") is False


@pytest.mark.unit
def test_authority_ignores_channels_that_are_not_table_channels():
    assert tc._authority("system:shout", "alice") is None


@pytest.mark.unit
def test_a_seat_at_one_table_does_not_subscribe_to_another():
    with patch.object(tc.dal_table, "seated_monikers", side_effect=lambda args, t, **k: ["alice"] if t == "t1" else []), \
         patch.object(tc, "_require_args", return_value=ARGS), \
         patch.object(tc, "_session_monikers", return_value=False):
        assert tc._authority("casino:table:t1:chat", "alice") is True
        assert tc._authority("casino:table:t2:chat", "alice") is False


# ---------------------------------------------------------------- subscribe and unsubscribe (unit)


@pytest.mark.unit
def test_subscribe_seat_subscribes_both_channels_and_unsubscribe_removes_both():
    state = ChannelState()
    tc.subscribe_seat(state, 7, "t1")
    assert 7 in channel_get_subscribers(state, "casino:table:t1:events")
    assert 7 in channel_get_subscribers(state, "casino:table:t1:chat")
    tc.unsubscribe_table(state, 7, "t1")
    assert 7 not in channel_get_subscribers(state, "casino:table:t1:events")
    assert 7 not in channel_get_subscribers(state, "casino:table:t1:chat")


# ---------------------------------------------------------------- integration (zoid6test)


def _migration_applied() -> bool:
    from bbsengine6 import database
    try:
        with database.connect(ARGS) as conn, database.cursor(conn) as cur:
            cur.execute(database.query(
                "SELECT 1 FROM information_schema.columns WHERE table_schema='engine' "
                "AND table_name='__channel' AND column_name='subscribe_restricted'"))
            return cur.fetchone() is not None
    except Exception:
        return False


requires_channel_migration = pytest.mark.skipif(
    not _migration_applied(),
    reason="bbsengine6 channel_access_migration.sql is not applied to zoid6test",
)


@requires_channel_migration
@pytest.mark.integration
def test_create_table_channels_makes_both_with_the_right_flags():
    table = _moniker()
    try:
        res = tc.create_table_channels(ARGS, table, owner="bjbed_a")
        assert all(r.get("success") for r in res.values()), res
        events = channel_module.ChannelService(ARGS).get_channel(tc.events_channel(table))
        chat = channel_module.ChannelService(ARGS).get_channel(tc.chat_channel(table))
        assert events["announce_only"] is True
        assert chat["subscribe_restricted"] is True
        assert chat["publish_requires_subscription"] is True
    finally:
        _delete_channels(table)


@requires_channel_migration
@pytest.mark.integration
def test_create_table_channels_is_idempotent():
    table = _moniker()
    try:
        tc.create_table_channels(ARGS, table, owner="bjbed_a")
        again = tc.create_table_channels(ARGS, table, owner="bjbed_a")
        assert all(r.get("success") for r in again.values())
        assert any(r.get("existed") for r in again.values())
    finally:
        _delete_channels(table)


def _delete_channels(table: str) -> None:
    from bbsengine6 import database
    with database.connect(ARGS) as conn, database.cursor(conn) as cur:
        for name in tc.table_channels(table):
            cur.execute(database.query("DELETE FROM $engine.__channel WHERE name = :n", n=name))


# ---------------------------------------------------------------- every game creates its channels (unit)


@pytest.mark.unit
@pytest.mark.parametrize("module_path, cls_name, game", [
    ("casino.tictactoe.service", "TictactoeService", "tictactoe"),
    ("casino.yahtzee.service", "YahtzeeService", "yahtzee"),
])
def test_quick_play_creates_the_table_channels(module_path, cls_name, game):
    """A new tictactoe or yahtzee table gets its events and chat channels, like blackjack and poker."""
    import importlib

    module = importlib.import_module(module_path)
    service_cls = getattr(module, cls_name)
    created = {"moniker": f"{game}-tc-1", "type": game}
    fake_table_service = type("T", (), {
        "create_table": lambda self, **kw: {"success": True, "table": created},
    })()
    with patch.object(tc, "create_table_channels", return_value={}) as make:
        svc = service_cls.__new__(service_cls)
        svc.args = ARGS
        svc._pool = None
        svc._table_service = fake_table_service
        svc._find_table_fn = lambda *a, **k: None
        svc._ensure_table("alice")
    make.assert_called_once_with(ARGS, created["moniker"], owner="alice")


# ---------------------------------------------------------------- session stores (unit)


@pytest.mark.unit
def test_watcher_check_works_with_bed_session_registry():
    """zoid6 wires bed's SessionRegistry, which has no is_watching. The check must still answer."""
    from bed.api.session import SessionRegistry
    from casino.api.handler import _watching_check

    reg = SessionRegistry()
    reg.bind(session_id="s1", websocket_id="w1", moniker="watcher", is_sysop=False)
    reg.bind(session_id="s2", websocket_id="w2", moniker="other", is_sysop=False)
    reg.add_spectator("s1", "tbl-1")
    check = _watching_check(reg)
    assert check("tbl-1", "watcher") is True
    assert check("tbl-1", "other") is False
    assert check("tbl-2", "watcher") is False


@pytest.mark.unit
def test_watcher_check_prefers_a_store_that_provides_is_watching():
    from casino.api.handler import _watching_check

    class Store:
        def is_watching(self, table_moniker, moniker):
            return (table_moniker, moniker) == ("t", "m")

    check = _watching_check(Store())
    assert check("t", "m") is True
    assert check("t", "x") is False


# ---------------------------------------------------------------- seats come from the owning store (unit)


@pytest.mark.unit
def test_poker_table_seats_come_from_the_poker_service():
    """A poker seat is in the poker service, not casino.map_cardtable_player, so the authority asks it."""
    with patch.object(tc, "_require_args", return_value=ARGS), \
         patch.object(tc, "_table_type", return_value="poker"), \
         patch("casino.services.poker.PokerService.seated_monikers", return_value=["bjbed_a"]), \
         patch.object(tc, "_is_watching", return_value=False):
        assert tc._authority("casino:table:poker-1:chat", "bjbed_a") is True
        assert tc._authority("casino:table:poker-1:chat", "outsider") is False


@pytest.mark.unit
def test_cash_table_seats_still_come_from_the_seat_table():
    with patch.object(tc, "_require_args", return_value=ARGS), \
         patch.object(tc, "_table_type", return_value="blackjack"), \
         patch.object(tc.dal_table, "seated_monikers", return_value=["alice"]), \
         patch.object(tc, "_is_watching", return_value=False):
        assert tc._authority("casino:table:t1:chat", "alice") is True
        assert tc._authority("casino:table:t1:chat", "mallory") is False
