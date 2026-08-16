# casino/tests/test_diag_slots_bed.py
#
# Diagnostic test driver: connect to bed at localhost:8765 (when
# available), drive slot ops through casino's API and CLI, capture the
# ``io.echo`` diagnostics emitted by
# ``casino.api._auth.check_access``, and emit the captured lines via
# ``io.echo`` so the transcript matches the rest of casino's output
# style (no ``print()`` bypasses the echo pipeline -- per AGENTS.md).
#
# Run interactively with:
#     pytest casino/tests/test_diag_slots_bed.py -v -s
#
# Skipped if bed is not reachable at localhost:8765.
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import websockets

from bbsengine6 import io

from casino.api._auth import check_access


BED_URL = "ws://localhost:8765/"
BED_HOST = "localhost"
BED_PORT = 8765


# ----- bed probe -----------------------------------------------------------


async def _probe_bed_async() -> bool:
    try:
        async with websockets.connect(BED_URL, open_timeout=3) as ws:
            await ws.send(json.dumps({"type": "ping"}))
            msg = await asyncio.wait_for(ws.recv(), timeout=3)
            return "pong" in msg
    except Exception as e:
        io.echo(f"[diag] bed probe failed: {type(e).__name__}: {e}", level="warning")
        return False


def probe_bed() -> bool:
    return asyncio.run(_probe_bed_async())


def build_args() -> argparse.Namespace:
    a = argparse.Namespace()
    a.bed_host = BED_HOST
    a.bed_port = BED_PORT
    a.bed_path = "/"
    a.bed_call_timeout = 5.0
    a.databasename = "test"
    a.database = "test"
    a.token_file = None
    return a


# ----- io.echo capture -----------------------------------------------------


class _EchoCapture:
    """Patch ``bbsengine6.io.echo`` (the canonical symbol the casino
    API handler imports via ``from bbsengine6 import io``) so every
    ``io.echo`` call lands in :attr:`lines`. Restore with :meth:`close`.
    """

    def __init__(self):
        self.lines = []
        import bbsengine6.io as bbs_io
        self._real_bbs_io_echo = bbs_io.echo

        def cap(text, *a, **kw):
            self.lines.append(str(text))

        bbs_io.echo = cap
        # casino imports ``from bbsengine6 import io`` then calls
        # ``io.echo``; the symbol lives on the io module's namespace.
        io.echo = cap

    def close(self):
        import bbsengine6.io as bbs_io
        bbs_io.echo = self._real_bbs_io_echo
        io.echo = self._real_bbs_io_echo

    def header(self, title: str) -> None:
        """Emit a section header inside the captured stream so the
        transcript shows which scenario produced each line.
        """
        self.lines.append(f"--- {title} ---")


# ----- scenarios -----------------------------------------------------------


def _scenario_no_token() -> dict | None:
    """User's bug: session bound, no wire / session token, BED mode,
    legacy off -> DENY gate no-claims.
    """
    secret = b"test-secret-do-not-use-in-prod"
    from casino.api._auth import mint_token_record
    record = mint_token_record(
        secret=secret, instance_id="diag-test",
        moniker="alice", session_id="s-alice", websocket_id="ws-1",
    )
    store = MagicMock()
    store.get = MagicMock(return_value=record)
    self_ref = MagicMock()
    self_ref.args = build_args()
    self_ref.secret = secret
    self_ref.token_store = store
    self_ref.instance_id = "diag-test"
    self_ref.allow_legacy_session_only = False
    self_ref.sessions = None

    ws = MagicMock()
    ws.id = "ws-1"
    ws._bbsengine6_session_id = 1

    state = MagicMock()
    state.moniker = "alice"
    state.is_sysop = False
    state.auth_service_token = None

    with patch("casino.api._auth._get_or_bind_session_for", return_value=(state, None)):
        _, err = check_access(self_ref, ws, "slot_spin", {"bet": 10})
    return err


def _scenario_wire_token() -> dict | None:
    """Valid wire token + BED mode -> claims-set via wire-token, then
    DENY policy forbidden (no seat).
    """
    secret = b"test-secret-do-not-use-in-prod"
    from casino.api._auth import mint_token_record, encode_token
    record = mint_token_record(
        secret=secret, instance_id="diag-test",
        moniker="alice", session_id="s-alice", websocket_id="ws-1",
    )
    store = MagicMock()
    store.get = MagicMock(return_value=record)
    self_ref = MagicMock()
    self_ref.args = build_args()
    self_ref.secret = secret
    self_ref.token_store = store
    self_ref.instance_id = "diag-test"
    self_ref.allow_legacy_session_only = False
    self_ref.sessions = None

    ws = MagicMock()
    ws.id = "ws-1"
    ws._bbsengine6_session_id = 1

    state = MagicMock()
    state.moniker = "alice"
    state.is_sysop = False
    state.auth_service_token = None

    token = encode_token({
        "version": 1, "moniker": "alice", "is_sysop": False,
        "session_id": "s-alice", "bed_instance_id": "diag-test",
        "websocket_id": "ws-1",
        "expires_at": 1_000_000.0, "issued_at": 1_000.0,
    }, secret)

    with patch("casino.api._auth._get_or_bind_session_for", return_value=(state, None)):
        _, err = check_access(self_ref, ws, "slot_spin", {
            "bet": 10, "token": token, "table_moniker": "slots-alice",
        })
    return err


def _scenario_door_mode() -> dict | None:
    """Door mode (no secret / store / inst), legacy opt-in ->
    gate-passed via legacy_session_only, then DENY policy.
    """
    self_ref = MagicMock()
    self_ref.args = build_args()
    self_ref.secret = None
    self_ref.token_store = None
    self_ref.instance_id = None
    self_ref.allow_legacy_session_only = True
    self_ref.sessions = None

    ws = MagicMock()
    ws.id = "ws-1"
    ws._bbsengine6_session_id = 1

    state = MagicMock()
    state.moniker = "alice"
    state.is_sysop = False
    state.auth_service_token = None

    with patch("casino.api._auth._get_or_bind_session_for", return_value=(state, None)):
        _, err = check_access(self_ref, ws, "slot_spin", {"bet": 10})
    return err


def _scenario_slot_cli() -> list:
    """Drive casino.commands.slots.lib.slot_spin end-to-end through the
    local CLI. The CLI gate passes (FakeClient is authenticated), the
    function calls ``client.cmd_slot_spin`` which schedules a WS send.
    The send is captured; the receive loop is also stubbed so the
    client does not deadlock waiting for a reply.

    Returns the list of wire messages the client would have sent.
    """
    from casino.commands.slots import lib as slots_lib

    class FakeClient:
        authenticated = True
        moniker = "alice"
        is_sysop = False
        balance = 1000
        _bearer_token = None
        current_table_moniker = None
        _ws = None
        _loop = MagicMock()

        def __init__(self):
            self.sent = []

        def cmd_slot_spin(self):
            self.sent.append({"type": "slot_spin", "bet": 10})

    client = FakeClient()
    args = build_args()

    with patch("casino.commands.slots.lib.get_client", return_value=client), \
         patch("casino.commands.slots.lib._casino_access", return_value=True):
        try:
            slots_lib.slot_spin(args, client=client)
        except Exception as e:
            io.echo(
                f"[diag] slot_spin raised: {type(e).__name__}: {e}",
                level="warning",
            )
    return client.sent


def _scenario_live_bed_no_auth() -> str:
    """Send a slot_spin to bed at localhost:8765 with no auth and
    capture the server reply. Verifies the wire path is reachable
    and the server-side gate behaves the same as the local one.
    """
    async def _go():
        async with websockets.connect(BED_URL, open_timeout=3) as ws:
            await ws.send(json.dumps({"type": "slot_spin", "bet": 10}))
            return await asyncio.wait_for(ws.recv(), timeout=3)
    return asyncio.run(_go())


# ----- the actual test -----------------------------------------------------


@pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX-only websockets probe"
)
def test_diag_slots_bed_diagnostics_via_localhost_8765():
    """Drive the three check_access scenarios + the slot CLI path,
    capturing every ``io.echo`` call so the transcript shows the
    mode / ws_id / wire_token / gate-decision lines emitted by the
    new diagnostics in ``casino.api._auth.check_access``.

    Bed at localhost:8765 is referenced in args (``bed_host``,
    ``bed_port``); the live round-trip is attempted only if bed is
    reachable.
    """
    cap = _EchoCapture()
    real_echo = cap._real_bbs_io_echo
    try:
        cap.header("scenario: user's bug (no token, BED mode, legacy off)")
        err = _scenario_no_token()
        cap.lines.append(f"[scenario-no-token] err={err}")

        cap.header("scenario: valid wire token, BED mode")
        err = _scenario_wire_token()
        cap.lines.append(f"[scenario-wire-token] err={err}")

        cap.header("scenario: door mode (legacy opt-in)")
        err = _scenario_door_mode()
        cap.lines.append(f"[scenario-door-mode] err={err}")

        cap.header("scenario: slot CLI end-to-end (FakeClient authenticated)")
        sent = _scenario_slot_cli()
        cap.lines.append(f"[scenario-slot-cli] wire messages sent={sent}")

        if probe_bed():
            cap.header("scenario: live bed at localhost:8765 (no auth)")
            try:
                reply = _scenario_live_bed_no_auth()
                cap.lines.append(f"[scenario-live-bed] reply={reply[:160]}")
            except Exception as e:
                cap.lines.append(
                    f"[scenario-live-bed] failed: {type(e).__name__}: {e}"
                )
        else:
            cap.lines.append("[scenario-live-bed] SKIPPED (bed unreachable)")
    finally:
        # Emit the captured transcript via the REAL io.echo (not
        # print) so it goes through the echo pipeline.
        cap.close()
        real_echo("=" * 60)
        real_echo("[diag] captured io.echo diagnostics (bed=" + BED_HOST + ":" + str(BED_PORT) + ")")
        real_echo("=" * 60)
        for line in cap.lines:
            real_echo(line)
        n_match = sum(1 for l in cap.lines if "[check_access]" in l)
        real_echo("=" * 60)
        real_echo(
            f"[diag] summary: {len(cap.lines)} captured lines, "
            f"{n_match} contain '[check_access]'"
        )
        real_echo("=" * 60)

    # Hard assertion: at least 4 [check_access] lines must have fired
    # (one per scenario minimum). If fewer, the diagnostics are not
    # wired into the installed casino -- fail loudly.
    assert n_match >= 4, (
        f"expected at least 4 [check_access] diagnostic lines, "
        f"got {n_match}. New diagnostics may not be wired."
    )
