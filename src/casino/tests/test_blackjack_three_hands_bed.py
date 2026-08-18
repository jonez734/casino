#!/usr/bin/env python3
# casino/tests/test_blackjack_three_hands_bed.py
# Bed-targeted companion to test_blackjack_three_hands.py.
#
# Connects to a running bed daemon (default ws://127.0.0.1:8765/),
# drives the same scenarios through bed's auth service + casino
# MessageRouter, and asserts the wire envelopes that come back.
#
# Skipped when bed is not reachable at the configured URI so it can
# sit in the test suite without breaking local CI runs that don't
# have bed running.
#
# IMPORTANT: bed loads casino modules at startup. After pulling new
# casino source (e.g. the ``__exists__`` sentinel in
# ``dal/table.create_table``) you MUST restart the bed daemon for
# the new code to take effect -- Python does not auto-reload modules
# in a running process. Without a restart, the duplicate-table test
# will fail with a unique-constraint violation on
# ``casino.__bank_table_pkey`` because bed's in-memory casino is
# still running the pre-sentinel code path.
#
# Env overrides:
#   CASINO_TEST_BED_URI  (default: ws://127.0.0.1:8765/)
#   CASINO_TEST_BED_DATABASE  (default: zoid6)
#
# Run interactively:
#   pytest casino/tests/test_blackjack_three_hands_bed.py -v -s

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import unittest
from typing import Optional

import pytest
import websockets

sys.path.insert(0, "/home/opencode/data/work/casino/src")
sys.path.insert(0, "/home/opencode/data/work/bbsengine6/py/src")
sys.path.insert(0, "/home/opencode/data/work/bed/src")

BED_URI = os.environ.get("CASINO_TEST_BED_URI", "ws://127.0.0.1:8765/")
BED_DATABASE = os.environ.get("CASINO_TEST_BED_DATABASE", "zoid6")
TEST_TABLE_PREFIX = "blackjack-bed-"
PROBE_TIMEOUT_S = 2.0
DEFAULT_TIMEOUT_S = 10.0


# ----- bed probe ------------------------------------------------------------


async def _probe_bed_async(uri: str) -> bool:
    try:
        async with websockets.connect(uri, open_timeout=PROBE_TIMEOUT_S) as ws:
            await ws.send(json.dumps({"type": "ping"}))
            raw = await asyncio.wait_for(ws.recv(), timeout=PROBE_TIMEOUT_S)
            return "pong" in raw
    except Exception:
        return False


def _probe_bed(uri: str) -> bool:
    return asyncio.run(_probe_bed_async(uri))


_BED_REACHABLE = _probe_bed(BED_URI)
_SKIP_REASON = (
    f"bed is not reachable at {BED_URI}; "
    "start the daemon or set CASINO_TEST_BED_URI to override"
)


# ----- websocket client -----------------------------------------------------


class _WsClient:
    """Minimal WebSocket client with a receive queue."""

    def __init__(self, uri: str, timeout: float = DEFAULT_TIMEOUT_S):
        self.uri = uri
        self.timeout = timeout
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self._rx: asyncio.Queue = asyncio.Queue()
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def connect(self) -> None:
        self.ws = await asyncio.wait_for(
            websockets.connect(self.uri, ping_interval=30, ping_timeout=10),
            timeout=self.timeout,
        )
        self._running = True
        self._task = asyncio.create_task(self._pump())

    async def _pump(self) -> None:
        try:
            async for raw in self.ws:
                if not self._running:
                    break
                try:
                    await self._rx.put(json.loads(raw))
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass
        finally:
            self._running = False

    async def send(self, payload: dict) -> None:
        if not self.ws or not self._running:
            raise ConnectionError("not connected")
        await self.ws.send(json.dumps(payload))

    async def recv(self, timeout: Optional[float] = None) -> dict:
        return await asyncio.wait_for(
            self._rx.get(), timeout=timeout or self.timeout
        )

    async def drain(self, max_count: int = 20, timeout: float = 1.5) -> list:
        out: list = []
        deadline = asyncio.get_event_loop().time() + timeout
        for _ in range(max_count):
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                break
            try:
                out.append(
                    await asyncio.wait_for(self._rx.get(), timeout=min(remaining, 0.25))
                )
            except asyncio.TimeoutError:
                break
        return out

    async def close(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        if self.ws:
            try:
                await self.ws.close(code=1000)
            except Exception:
                pass


# ----- the test -------------------------------------------------------------


@pytest.mark.integration
@unittest.skipUnless(_BED_REACHABLE, _SKIP_REASON)
class TestBlackjackThreeHandsBed(unittest.IsolatedAsyncioTestCase):
    """Drive the bed + casino stack with the duplicate-table scenario.

    Skipped automatically when bed is unreachable. Each test connects
    a fresh WebSocket so server-side session bindings don't leak
    between cases.
    """

    def _args(self) -> argparse.Namespace:
        return argparse.Namespace(
            bed_host="127.0.0.1",
            bed_port=8765,
            bed_path="/",
            databasename=BED_DATABASE,
        )

    async def _authenticate(self, client: _WsClient, moniker: str, password: str) -> dict:
        await client.send({"type": "auth", "moniker": moniker, "password": password})
        return await client.recv()

    async def _create_table(
        self, client: _WsClient, *, game_type: str, moniker: str,
        min_bet: int = 10, max_bet: int = 1000,
    ) -> dict:
        await client.send(
            {
                "type": "create_table",
                "game_type": game_type,
                "min_bet": min_bet,
                "max_bet": max_bet,
                "moniker": moniker,
            }
        )
        return await client.recv()

    async def test_bed_create_duplicate_blackjack_table_returns_table_exists(self):
        """Through a live bed + casino router: jam creates a blackjack
        table; the second create with the same moniker comes back as
        ``type=table_exists`` with the existing owner's metadata.
        """
        client = _WsClient(BED_URI)
        await client.connect()
        try:
            auth = await self._authenticate(client, "jam", "test")
            self.assertEqual(auth.get("type"), "auth_result", auth)
            self.assertTrue(auth.get("success"), auth)
            self.assertEqual(auth.get("moniker"), "jam")

            dup_moniker = f"{TEST_TABLE_PREFIX}dup-bed-{int(time.time() * 1000)}"

            first = await self._create_table(
                client, game_type="blackjack", moniker=dup_moniker,
            )
            self.assertEqual(
                first.get("type"),
                "table_created",
                f"first create through bed: {first}",
            )
            self.assertEqual(first.get("moniker"), dup_moniker)

            await client.drain(max_count=20, timeout=1.5)

            second = await self._create_table(
                client, game_type="blackjack", moniker=dup_moniker,
            )
            self.assertEqual(
                second.get("type"),
                "table_exists",
                f"second create through bed: {second}",
            )
            self.assertEqual(second.get("moniker"), dup_moniker)
            self.assertEqual(second.get("game_type"), "blackjack")
            self.assertEqual(second.get("owner"), "jam")
            self.assertIn("stats", second)
            self.assertIsInstance(second["stats"], dict)
            self.assertIn(dup_moniker, second.get("message", ""))

            await client.drain(max_count=10, timeout=1.0)
            mismatch = await self._create_table(
                client, game_type="yahtzee", moniker=dup_moniker,
            )
            self.assertEqual(
                mismatch.get("type"), "error", mismatch,
            )
            self.assertEqual(mismatch.get("code"), "type_mismatch")
        finally:
            await client.close()


if __name__ == "__main__":
    unittest.main()
