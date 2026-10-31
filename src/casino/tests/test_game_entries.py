"""Game console scripts run through bed, and handle a refused login gracefully.

- Each game entry (``blackjack_main`` and the rest) runs ``casino <game> [...]``.
- A refused login stops the session before the command runs, with one line.
- With bed unreachable, every game exits 1 with one line and no traceback.
"""

import argparse
import asyncio
import os
import subprocess
import sys
from unittest.mock import patch

import pytest

from casino import __main__ as casino_main
from casino.client import casino_client as cc

pytestmark = pytest.mark.unit

GAMES = ("blackjack", "poker", "slots", "tictactoe", "yahtzee")
SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BIN = os.path.abspath(os.path.join(SRC, "..", "bin"))


def _args():
    return argparse.Namespace(bed_host="localhost", bed_port=1, bed_path="/", token_file=None,
                              bed_call_timeout=5.0, bed_probe_timeout=0.25)


def _session_client():
    """A client with no loop of its own: ``_session`` creates the loop, and its
    ``finally`` closes it. The network calls are stubbed, so no socket opens.
    """
    return cc.CasinoClient(_args())


@pytest.mark.parametrize("game", GAMES)
def test_game_entry_routes_to_its_command_package(game):
    with patch.object(casino_main, "main", return_value=0) as main:
        getattr(casino_main, f"{game}_main")(["--version"])
    main.assert_called_once_with([game, "--version"])


@pytest.mark.parametrize("game", GAMES)
def test_shim_exists_and_is_executable(game):
    path = os.path.join(BIN, game)
    assert os.path.exists(path), path
    assert os.access(path, os.X_OK), path
    with open(path) as fh:
        assert f"{game}_main" in fh.read()


def test_refused_login_does_not_run_the_command():
    client = _session_client()
    ran = []

    async def connect():
        return True

    async def refuse():
        client.authenticated = False

    with patch.object(client, "connect", connect), \
         patch.object(client, "receive_loop", lambda: asyncio.sleep(0)), \
         patch.object(client, "cmd_auth", refuse), \
         patch.object(cc, "_ensure_client_screen"), \
         patch.object(cc.io, "echo") as echo:
        client.run_once(lambda: ran.append("command"))
    assert ran == []
    assert client._exit_reason == "auth_failed"
    assert any("not logged in" in str(c.args[0]) for c in echo.call_args_list if c.args)


def test_successful_login_runs_the_command():
    client = _session_client()
    ran = []

    async def connect():
        return True

    async def accept():
        client.authenticated = True

    with patch.object(client, "connect", connect), \
         patch.object(client, "receive_loop", lambda: asyncio.sleep(0)), \
         patch.object(client, "cmd_auth", accept), \
         patch.object(cc, "_ensure_client_screen"), \
         patch.object(cc.io, "echo"):
        client.run_once(lambda: ran.append("command"))
    assert ran == ["command"]


@pytest.mark.parametrize("game", GAMES)
def test_bed_down_exits_one_with_one_line(game):
    env = dict(os.environ, PYTHONPATH=SRC)
    proc = subprocess.run(
        [sys.executable, os.path.join(BIN, game), "--bed-host", "localhost", "--bed-port", "1"],
        capture_output=True, text=True, timeout=60, env=env,
    )
    text = proc.stdout + proc.stderr
    assert proc.returncode == 1, text
    assert "Traceback" not in text
    assert "bed daemon" in text
