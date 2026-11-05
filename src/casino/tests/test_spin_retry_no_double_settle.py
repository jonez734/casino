"""A slot spin retried with the same correlation id is settled once.

Runs scripts/check-spin-retry.py against the test database, and checks in the settle function's
SQL that the duplicate check comes before the balance change. Skipped when no test database is set.
"""

import os
import re
import unittest
from pathlib import Path

import pytest

SQL = Path(__file__).resolve().parents[1] / "sql" / "casino_settle_spin_functions.sql"
DB = os.environ.get("CASINO_TEST_DB") or os.environ.get("CASINO_RETRY_CHECK_DB")


def _code(text: str) -> str:
    return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("--"))


def test_duplicate_check_runs_before_the_balance_change():
    text = _code(SQL.read_text())
    dedupe = text.index("FROM casino.__slot_spin s")
    move = text.index("UPDATE bank.__account SET balance = balance + v_net")
    assert dedupe < move, "the correlation-id check must come before any money moves"


def test_slot_spin_has_a_unique_correlation_id_index():
    text = _code((Path(__file__).resolve().parents[1] / "sql" / "slots.sql").read_text())
    assert re.search(r"create unique index if not exists uq_slot_spin_correlation", text, re.IGNORECASE)


@pytest.mark.skipif(not DB, reason="set CASINO_TEST_DB to run the retry checks against a test database")
def test_retry_checker_all_cases_pass():
    import subprocess
    import sys

    script = Path(__file__).resolve().parents[2].parent / "scripts" / "check-spin-retry.py"
    out = subprocess.run([sys.executable, str(script), "--db", DB], capture_output=True, text=True, timeout=110)
    assert out.returncode == 0, out.stdout + out.stderr
    assert "5 passed, 0 failed" in out.stdout
