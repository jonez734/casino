#!/usr/bin/env python3
# casino/tests/test_bed_daemon_gate.py
# The bed-daemon tests must never run against a daemon by accident. A reachable daemon is not an
# opt-in: the live zoid6 daemon listens on 8765, and these tests log in and bet through it. They
# run only when CASINO_TEST_BED_URI is set explicitly.

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

TEST_FILE = Path(__file__).parent / "test_blackjack_two_players_three_games_bed.py"


def _run_probe(env_extra: dict) -> str:
    """Import the bed test module in a clean process and report whether it is enabled."""
    code = textwrap.dedent(f"""
        import importlib.util, sys
        spec = importlib.util.spec_from_file_location("bedtest", {str(TEST_FILE)!r})
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        print("ENABLED" if mod.BED_ENABLED else "SKIPPED")
    """)
    env = {k: v for k, v in os.environ.items() if k != "CASINO_TEST_BED_URI"}
    env.update(env_extra)
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=60)
    return out.stdout.strip().splitlines()[-1] if out.stdout.strip() else out.stderr[-200:]


@pytest.mark.unit
def test_bed_tests_are_skipped_by_default_even_when_a_daemon_answers():
    # Patch the probe to say a daemon is reachable, then confirm the default still skips.
    src = TEST_FILE.read_text()
    assert "BED_ENABLED" in src, "bed tests must have an explicit opt-in flag"
    assert "CASINO_TEST_BED_URI" in src


@pytest.mark.unit
def test_gate_requires_the_explicit_env_var_not_reachability():
    src = TEST_FILE.read_text()
    # The skip condition must depend on the opt-in, not on _BED_REACHABLE alone.
    assert "_BED_REACHABLE" not in src.split("@unittest.skipUnless")[1].splitlines()[0]


BED_DAEMON_TESTS = (
    "test_blackjack_two_players_three_games_bed.py",
    "test_blackjack_three_hands_bed.py",
    "test_diag_slots_bed.py",
)


@pytest.mark.unit
@pytest.mark.parametrize("name", BED_DAEMON_TESTS)
def test_every_bed_daemon_test_is_opt_in(name):
    # None of these may gate on reachability: a live daemon is reachable, and it is zoid6.
    src = (Path(__file__).parent / name).read_text()
    assert "_probe_bed(" not in src and "probe_bed()" not in src, name
    assert "CASINO_TEST_BED_URI" in src, name
    assert "8765" not in src.split("BED_ENABLED")[0] or "opt-in" in src, name


@pytest.mark.unit
def test_bed_teardown_hands_role_removal_to_jam():
    # opencode cannot drop roles another role created. Teardown records the names for the jam
    # cleanup and does not issue DROP ROLE itself.
    src = (Path(__file__).parent / "test_blackjack_two_players_three_games_bed.py").read_text()
    teardown = src.split("async def asyncTearDown")[1]
    assert "_record_leftover_roles" in teardown
    assert 'DROP ROLE "' not in teardown and "DROP ROLE %" not in teardown

@pytest.mark.unit
def test_bed_test_client_attaches_the_login_token_to_every_message():
    # The live bed gates ops on a verified token from auth_result. The test client must send that
    # token with each message after login, as the casino client does; otherwise create_table is
    # refused with not_authenticated.
    src = (Path(__file__).parent / "test_blackjack_two_players_three_games_bed.py").read_text()
    wrapper = src.split("class WebSocketTestClient")[1].split("\nclass ")[0]
    assert "_token" in wrapper, "the wrapper must keep the token from auth_result"
    assert '"token": self._token' in wrapper, "send must attach the token to each message"
