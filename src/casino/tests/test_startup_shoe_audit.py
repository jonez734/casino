# casino/tests/test_startup_shoe_audit.py
# Pins the startup contract for poker state and the shoe audit log: startup runs the shoe audit
# migration, and that migration gives bed everything the daemon needs on the tables it uses,
# including INSERT and DELETE on casino.__table (poker creates and removes table rows).

from __future__ import annotations

import re
from pathlib import Path

import casino

ROOT = Path(casino.__file__).resolve().parent
MIGRATION = ROOT / "sql" / "shoe_audit_migration.sql"
STARTUP = ROOT / "startup" / "main.py"


def test_startup_runs_the_shoe_audit_migration():
    assert '"shoe_audit_migration.sql"' in STARTUP.read_text(encoding="utf-8")


def test_the_migration_file_exists():
    assert MIGRATION.is_file()


def _grants_to(role: str, text: str) -> set[tuple[str, str]]:
    """(object, privilege) pairs the migration grants to ``role``."""
    out: set[tuple[str, str]] = set()
    for stmt in re.findall(r"grant\s+([^;]+);", text, flags=re.IGNORECASE):
        m = re.match(r"(.+?)\s+on\s+(\S+)\s+to\s+(.+)$", stmt.strip(), flags=re.IGNORECASE | re.DOTALL)
        if not m:
            continue
        privs, obj, roles = m.group(1), m.group(2), m.group(3)
        if role in [r.strip() for r in roles.split(",")]:
            for p in privs.split(","):
                out.add((obj, p.strip().lower()))
    return out


def test_bed_can_create_and_remove_poker_table_rows():
    granted = _grants_to("bed", MIGRATION.read_text(encoding="utf-8"))
    for priv in ("select", "insert", "update", "delete"):
        assert ("casino.__table", priv) in granted, f"bed needs {priv} on casino.__table"


def test_bed_can_write_poker_state_and_the_shoe_log():
    granted = _grants_to("bed", MIGRATION.read_text(encoding="utf-8"))
    for priv in ("select", "insert", "update", "delete"):
        assert ("casino.__poker_state", priv) in granted
    assert ("casino.__shoe_event", "insert") in granted


def test_the_owner_move_runs_again_after_the_shoe_migration():
    """The shoe migration creates tables. They must be moved to zoid6 by a later owner pass, or they
    stay owned by the login role that ran the migration and bed's grants on the schema do not reach
    them as zoid6 expects."""
    text = STARTUP.read_text(encoding="utf-8")
    shoe = text.index('"shoe_audit_migration.sql"')
    owner_passes = [m.start() for m in re.finditer(r'"owner_zoid6_migration.sql"', text)]
    assert any(p > shoe for p in owner_passes), "no owner pass after the shoe migration"
