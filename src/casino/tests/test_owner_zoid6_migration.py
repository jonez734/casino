#!/usr/bin/env python3
# casino/tests/test_owner_zoid6_migration.py
# casino --install moves every casino object to zoid6, the schema owner.
# Source-level checks: no database is touched.

from pathlib import Path

CASINO = Path(__file__).resolve().parents[1]
SQL = CASINO / "sql" / "owner_zoid6_migration.sql"
STARTUP = CASINO / "startup" / "main.py"


def _sql():
    return SQL.read_text()


def test_migration_file_exists_and_is_packaged():
    assert SQL.is_file()
    # pyproject ships sql/*.sql, so the file is included in the installed build.
    text = (CASINO.parents[1] / "pyproject.toml").read_text()
    assert '"sql/*.sql"' in text


def test_migration_only_moves_casino_objects():
    sql = _sql()
    # The catalog filter and every ALTER target are the casino schema only.
    assert "n.nspname = 'casino'" in sql
    assert sql.count("casino.%I") >= 4
    assert "'engine'" not in sql and "'bank'" not in sql


def test_migration_moves_tables_views_sequences_and_functions():
    sql = _sql()
    for kind in ("alter sequence", "alter view", "alter table", "alter function"):
        assert kind in sql, kind
    assert "owner to zoid6" in sql


def test_migration_is_idempotent_by_owner_filter():
    sql = _sql()
    assert "pg_get_userbyid(c.relowner) <> 'zoid6'" in sql
    assert "pg_get_userbyid(p.proowner) <> 'zoid6'" in sql


def test_startup_runs_migration_after_classes_and_before_overrides():
    src = STARTUP.read_text()
    classes_at = src.index("for c, sql in classlist:")
    migrate_at = src.index('"owner_zoid6_migration.sql"')
    channels_at = src.index("checkchannels.main(args, conn=conn)")
    assert classes_at < migrate_at < channels_at


def test_startup_migration_failure_stops_install():
    src = STARTUP.read_text()
    window = src[src.index('"owner_zoid6_migration.sql"') - 200:src.index('"owner_zoid6_migration.sql"') + 300]
    assert "return False" in window
