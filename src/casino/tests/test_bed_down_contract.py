"""Casino needs bed. With bed unreachable it says so in one line and exits 1.

No traceback reaches the operator, and no message suggests a door mode that no
longer exists.
"""

import argparse
import asyncio
from unittest.mock import patch

import pytest

from bbsengine6.net.ping import PingUnavailable
from bed.tools._routing import BedNotReachable

from casino import __main__ as casino_main
from casino.client import casino_client as cc

pytestmark = pytest.mark.unit


def _args(port=1):
    return argparse.Namespace(bed_host="localhost", bed_port=port, bed_path="/",
                              bed_call_timeout=5.0, bed_probe_timeout=0.25, token_file=None)


def test_connect_failure_prints_one_line_and_no_traceback():
    client = cc.CasinoClient(_args())
    client._loop = asyncio.new_event_loop()
    try:
        exc = PingUnavailable("localhost", 1, OSError("refused"), prog="casino")
        with patch.object(cc, "_net_connect", side_effect=exc), \
             patch.object(cc.io, "echo") as echo, \
             patch.object(cc.io, "echo_traceback") as tb:
            ok = client._loop.run_until_complete(client.connect())
    finally:
        client._loop.close()
    assert ok is False
    tb.assert_not_called()
    messages = [c.args[0] for c in echo.call_args_list if c.args]
    assert any("bed daemon" in m for m in messages)


def test_menu_entry_with_bed_unreachable_exits_1_with_one_line():
    """The real ``python -m casino`` with bed unreachable: one line, exit 1, no traceback."""
    import os
    import subprocess
    import sys

    src = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    env = dict(os.environ, PYTHONPATH=src)
    proc = subprocess.run(
        [sys.executable, "-m", "casino", "--bed-host", "localhost", "--bed-port", "1"],
        capture_output=True, text=True, timeout=60, env=env,
    )
    text = proc.stdout + proc.stderr
    assert proc.returncode == 1, text
    assert "Traceback" not in text
    assert "bed is not reachable at localhost:1" in text
    assert "--direct" not in text
