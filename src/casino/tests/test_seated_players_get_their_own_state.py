"""A table's game_state reaches each seated player's own socket with that player's hand.

The table broadcast carries no player's hand, so a seated player's client overwrote its own hand with an
empty one. The fix sends every seated player their own view through the transport, by session id, and
keeps the public broadcast for watchers. Tests use stand-ins; no socket or database is touched.
"""

import asyncio
from types import SimpleNamespace

import pytest

from casino.api import handler as h


pytestmark = pytest.mark.unit


class _Sessions:
    """Stands in for bed's SessionRegistry: moniker -> session ids."""

    def __init__(self, by_moniker):
        self._by_moniker = by_moniker

    def sessions_for_moniker(self, moniker):
        return list(self._by_moniker.get(moniker, []))


class _Transport:
    """Stands in for the transport: records each send_to_session call."""

    def __init__(self):
        self.sent = []

    async def send_to_session(self, session_id, message):
        self.sent.append((session_id, message))


class _Game:
    """Each player's view: the hand is theirs, the public view has none."""

    def get_game_state(self, table, player, *, deal=True):
        hands = {"alice": ["9H", "3C"], "bob": ["KD", "2S"]}
        return SimpleNamespace(to_dict=lambda: {
            "table_moniker": table,
            "phase": "playing",
            "player_hand": hands.get(player, []),
        })


def _handler(sessions, seated):
    from casino.dal import table as dal_table

    obj = h.GameServiceHandler.__new__(h.GameServiceHandler)
    obj.sessions = sessions
    obj.game_service = _Game()
    obj.game_service._pool = None
    obj.args = SimpleNamespace()
    obj.transport = _Transport()
    dal_table.seated_monikers = lambda *a, **k: seated
    return obj


def test_each_seated_player_gets_their_own_hand():
    sessions = _Sessions({"alice": ["conn-1"], "bob": ["conn-2"]})
    obj = _handler(sessions, ["alice", "bob"])

    asyncio.run(obj._send_each_seat_its_state(obj.transport, "blackjack-a"))

    sent = dict(obj.transport.sent)
    assert sent["conn-1"]["player_hand"] == ["9H", "3C"]
    assert sent["conn-2"]["player_hand"] == ["KD", "2S"]
    assert all(m["type"] == "game_state" for m in sent.values())


def test_a_seated_player_with_no_live_session_is_skipped():
    sessions = _Sessions({"alice": ["conn-1"]})
    obj = _handler(sessions, ["alice", "bob"])

    asyncio.run(obj._send_each_seat_its_state(obj.transport, "blackjack-a"))

    assert [sid for sid, _ in obj.transport.sent] == ["conn-1"]


def test_a_bet_sends_each_seated_player_their_own_hand(monkeypatch):
    # The bet path: after a bet, the seats each get their own view, not the empty table broadcast alone.
    from casino.dal import table as dal_table

    class _Bet(h.BetServiceHandler):
        def __init__(self):
            self.sessions = _Sessions({"alice": ["conn-1"], "bob": ["conn-2"]})
            self.game_service = _Game()
            self.args = SimpleNamespace()

    monkeypatch.setattr(dal_table, "seated_monikers", lambda *a, **k: ["alice", "bob"])
    bet = _Bet()
    bet.game_service._pool = None
    bet.args = SimpleNamespace()
    server = _Transport()
    asyncio.run(bet._send_each_seat_its_state(server, "blackjack-a"))

    sent = dict(server.sent)
    assert sent["conn-1"]["player_hand"] == ["9H", "3C"]
    assert sent["conn-2"]["player_hand"] == ["KD", "2S"]


def test_handle_bet_sends_the_seats_their_own_state(monkeypatch):
    # Drive the real _handle_bet: after a bet, every seated player is sent their own hand.
    from casino import access as access_mod
    from casino.dal import table as dal_table

    class _Bettor(h.BetServiceHandler):
        def __init__(self):
            self.sessions = _Sessions({"alice": ["conn-1"], "bob": ["conn-2"]})
            self.game_service = _BettingGame()
            self.args = SimpleNamespace()
            self._pool = None
            self.round_event_log = None

        def _check_access(self, websocket, op, message):
            return SimpleNamespace(moniker="alice", table_moniker="blackjack-a", is_sysop=False), None

        def _legacy_session_id(self, websocket):
            return 1

        def _drain_round_events(self):
            return None

        def _get_observers(self, table):
            return set()

        def _get_player_count(self, table):
            return 2

        async def _publish_to_table(self, *a, **k):
            return None

    class _BettingGame(_Game):
        _pool = None

        def place_bet(self, table, player, amount):
            return {"success": True, "message": "bet placed"}

        def take_settled_round(self, table):
            return None

    class _Socket:
        id = 1
        sent = []

        async def send(self, text):
            self.sent.append(text)

    monkeypatch.setattr(dal_table, "seated_monikers", lambda *a, **k: ["alice", "bob"])
    monkeypatch.setattr(access_mod, "_seated_table", lambda *a, **k: "blackjack-a")
    bettor = _Bettor()
    server = _Transport()

    asyncio.run(bettor._handle_bet(_Socket(), {"type": "bet", "amount": 10}, server=server))

    sent = dict(server.sent)
    assert sent["conn-2"]["player_hand"] == ["KD", "2S"], f"bob (seated, not the bettor) got {sent.get("conn-2")}"


def test_the_public_state_goes_to_watchers_not_to_the_table_channel(monkeypatch):
    # A seated player must not get the public broadcast (it carries no hand); a watcher gets it.
    from casino.dal import table as dal_table

    class _Watchers(_Sessions):
        def get_table_observers(self, table):
            return {"conn-9"}

    class _Bettor(h.BetServiceHandler):
        def __init__(self):
            self.sessions = _Watchers({"alice": ["conn-1"], "bob": ["conn-2"]})
            self.game_service = _BettingGame()
            self.args = SimpleNamespace()
            self._pool = None
            self.round_event_log = None
            self.published_to_channel = []

        def _check_access(self, websocket, op, message):
            return SimpleNamespace(moniker="alice", table_moniker="blackjack-a", is_sysop=False), None

        def _legacy_session_id(self, websocket):
            return 1

        def _drain_round_events(self):
            return None

        def _get_player_count(self, table):
            return 2

        async def _publish_to_table(self, *a, **k):
            self.published_to_channel.append(a)

    class _BettingGame(_Game):
        _pool = None

        def place_bet(self, table, player, amount):
            return {"success": True, "message": "bet placed"}

        def take_settled_round(self, table):
            return None

    class _Socket:
        id = 1

        async def send(self, text):
            return None

    monkeypatch.setattr(dal_table, "seated_monikers", lambda *a, **k: ["alice", "bob"])
    from casino import access as access_mod
    monkeypatch.setattr(access_mod, "_seated_table", lambda *a, **k: "blackjack-a")
    bettor = _Bettor()
    server = _Transport()

    asyncio.run(bettor._handle_bet(_Socket(), {"type": "bet", "amount": 10}, server=server))

    assert bettor.published_to_channel == [], "the public state must not go to the whole table channel"
    watcher_states = [m for sid, m in server.sent if sid == "conn-9"]
    assert watcher_states and watcher_states[0]["type"] == "game_state"
