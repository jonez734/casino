# casino/tests/test_poker_two_players_daemon.py
# Two players (bjbed_a, bjbed_b) play 10 scripted holdem hands over the live bed daemon.
#
# Opt-in: runs only when CASINO_TEST_BED_URI is set to a daemon started against the database the
# fixtures live on. Each player authenticates through the real auth flow and sends only
# poker_* messages. Prints every action and result.

from __future__ import annotations

import asyncio
import json
import os
import sys

import pytest
import websockets

BED_URI = os.environ.get("CASINO_TEST_BED_URI", "")
NUM_HANDS = 10
BUY_IN = 500
TABLE = "poker-daemon-2p"
PLAYERS = ("bjbed_a", "bjbed_b")
PASSWORD_FILE = os.path.join(os.path.expanduser("~"), ".config", "casino", "test-data", "bed-fixtures.json")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not BED_URI, reason="set CASINO_TEST_BED_URI to the daemon URI to run"),
]


class Player:
    def __init__(self, moniker: str, password: str):
        self.moniker = moniker
        self.password = password
        self.ws = None
        self.token = None
        self.log: list = []

    async def connect(self):
        self.ws = await websockets.connect(BED_URI, open_timeout=10)
        await self.ws.send(json.dumps({"type": "auth", "moniker": self.moniker, "password": self.password}))
        auth = await self._recv_type("auth_result")
        assert auth.get("type") == "auth_result" and auth.get("token"), f"{self.moniker} auth: {auth}"
        self.token = auth["token"]

    async def send(self, payload: dict) -> dict:
        await self.ws.send(json.dumps({**payload, "token": self.token}))
        return await self._recv_type(None)

    async def _recv_type(self, want):
        # Skip broadcast traffic (table/channel events) until the reply we want arrives.
        while True:
            msg = json.loads(await asyncio.wait_for(self.ws.recv(), 15))
            if want is None and msg.get("type") in ("poker_table_list", "poker_table_created",
                                                    "poker_joined_table", "poker_left_table",
                                                    "poker_hand_started", "poker_state",
                                                    "poker_action_result", "error"):
                return msg
            if want is not None and msg.get("type") == want:
                return msg

    async def close(self):
        if self.ws:
            await self.ws.close()


def _load_passwords() -> dict:
    with open(PASSWORD_FILE, encoding="utf-8") as f:
        raw = json.load(f)
    return {m: raw[m]["password"] for m in PLAYERS}


async def _play(a: Player, b: Player) -> list:
    out = []
    created = await a.send({"type": "poker_create_table", "variant": "holdem",
                            "betting_structure": "no_limit", "small_blind": 1, "big_blind": 2})
    print(f"create: {created}")
    assert created.get("type") != "error", created
    table = created.get("table_moniker")
    assert table, created

    for p in (a, b):
        joined = await p.send({"type": "poker_join_table", "table_moniker": table, "buy_in": BUY_IN})
        print(f"{p.moniker} join: {joined}")
        assert joined.get("type") != "error" and joined.get("success"), joined

    plays = (_hand_raise_call_check, _hand_raise_fold, _hand_call_bet_showdown)
    for n in range(1, NUM_HANDS + 1):
        play = plays[(n - 1) % len(plays)]
        started = await a.send({"type": "poker_start_hand", "table_moniker": table})
        print(f"\n--- hand {n} ({play.__name__}) started: {started}")
        assert started.get("success"), started
        outcome = await play(a, b, table)
        state = await a.send({"type": "poker_get_state", "table_moniker": table})
        chips = {p["moniker"]: p["credits"] for p in state.get("players", [])}
        total = sum(chips.values())
        print(f"hand {n} result: stage={state.get('game_stage')} chips={chips} total={total}")
        assert total == BUY_IN * len(PLAYERS), f"hand {n} chip total {total}"
        out.append((n, play.__name__, chips))
    return out


async def _act(p: Player, table: str, action: str, amount: int = 0) -> dict:
    payload = {"type": f"poker_{action}", "table_moniker": table}
    if action in ("bet", "raise"):
        payload["amount"] = amount
    res = await p.send(payload)
    print(f"  {p.moniker} {action}{' ' + str(amount) if amount else ''}: {res.get('message', res)}")
    assert res.get("success") or res.get("type") == "poker_action_result" and res.get("success"), res
    return res


async def _state(a: Player, table: str) -> dict:
    return await a.send({"type": "poker_get_state", "table_moniker": table})


def _seat_of(state: dict, a: Player, b: Player) -> Player:
    """The player the daemon says must act now."""
    return a if state.get("current_player") == a.moniker else b


async def _hand_raise_call_check(a: Player, b: Player, table: str) -> dict:
    state = await _state(a, table)
    cur = _seat_of(state, a, b)
    other = b if cur is a else a
    await _act(cur, table, "raise", 6)
    await _act(other, table, "call")
    while True:
        state = await _state(a, table)
        if state.get("game_stage") == "showdown" or not state.get("current_player"):
            break
        await _act(_seat_of(state, a, b), table, "check")
    return {"stage": state.get("game_stage")}


async def _hand_raise_fold(a: Player, b: Player, table: str) -> dict:
    state = await _state(a, table)
    cur = _seat_of(state, a, b)
    other = b if cur is a else a
    await _act(cur, table, "raise", 6)
    await _act(other, table, "fold")
    return {"stage": "showdown"}


async def _hand_call_bet_showdown(a: Player, b: Player, table: str) -> dict:
    state = await _state(a, table)
    cur = _seat_of(state, a, b)
    other = b if cur is a else a
    await _act(cur, table, "call")
    await _act(other, table, "call")
    while True:
        state = await _state(a, table)
        if state.get("game_stage") == "showdown" or not state.get("current_player"):
            break
        cur = _seat_of(state, a, b)
        other = b if cur is a else a
        await _act(cur, table, "bet", 4)
        await _act(other, table, "call")
    return {"stage": state.get("game_stage")}


@pytest.mark.integration
def test_two_players_ten_hands_daemon():
    passwords = _load_passwords()

    async def run():
        a = Player("bjbed_a", passwords["bjbed_a"])
        b = Player("bjbed_b", passwords["bjbed_b"])
        await a.connect()
        await b.connect()
        try:
            return await _play(a, b)
        finally:
            await a.close()
            await b.close()

    results = asyncio.run(run())
    assert len(results) == NUM_HANDS
