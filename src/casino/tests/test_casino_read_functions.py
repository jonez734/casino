"""bed reaches casino tables through a zoid6-owned SECURITY DEFINER function.

bed holds no table privileges on casino.__table. engine.casino_read takes the
token hash, reads the acting moniker from engine.__bed_token, shows hidden tables
only to a sysop (the engine.bed_is_sysop check), and refuses unknown ops.

The behaviour is checked against a database by the install and smoke runs; these
tests pin the contract in source so a refactor cannot silently widen it.
"""

import inspect
import re
from pathlib import Path

import casino
from casino import startup as casino_startup

SQL = Path(casino.__file__).parent / "sql" / "casino_read_functions.sql"


def _code(text: str) -> str:
    return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("--"))


def _text() -> str:
    return _code(SQL.read_text())


def test_function_is_security_definer_owned_by_zoid6():
    t = _text()
    assert "SECURITY DEFINER" in t
    assert "OWNER TO zoid6" in t


def test_bed_is_the_only_grantee():
    t = _text()
    assert "REVOKE ALL ON FUNCTION engine.casino_read(bytea, text, jsonb) FROM PUBLIC" in t
    assert "GRANT EXECUTE ON FUNCTION engine.casino_read(bytea, text, jsonb) TO bed" in t


def test_actor_comes_from_the_token_row_not_the_request():
    t = _text()
    assert "FROM engine.__bed_token t" in t
    assert "t.token_hash = p_token_hash" in t
    assert "p_args->>'moniker'" in t  # the target only, never the actor


def test_hidden_tables_are_sysop_only_in_both_ops():
    t = _text()
    # The rule appears once per op (list and get), with the table alias.
    assert len(re.findall(r"v_sysop OR t\.hidden IS NULL OR t\.hidden = false", t)) == 2
    assert "engine.bed_is_sysop(v_actor)" in t


def test_unknown_op_is_refused():
    assert "unknown op %" in _text()


def test_token_refusal_names_the_failing_op():
    assert "casino_read(%): no live session for this token', p_op" in _text()


def test_casino_startup_installs_the_read_function_after_the_owner_migration():
    src = inspect.getsource(casino_startup.main)
    assert "casino_read_functions.sql" in src
    assert src.index("owner_zoid6_migration.sql") < src.index("casino_read_functions.sql")


def test_function_reads_only_casino_table_not_bank_or_engine_member():
    t = _text()
    assert re.search(r"FROM\s+casino\.__table", t)
    assert "bank." not in t
