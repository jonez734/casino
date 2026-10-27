#!/usr/bin/env python3
# casino/tests/test_cleanup_test_state.py
# casino --cleanup-test-state: opencode removes what it can, reports the rest, and writes a jam
# file for the rest. These tests cover the pure logic (name pattern, the six pristine checks, the
# report, the jam file, the live-database gate). No database.

import re
from pathlib import Path

import pytest

from casino import cleanup_test_state as cts


@pytest.mark.unit
@pytest.mark.parametrize(
    "name, matches",
    [
        ("bjbed_a", True),
        ("m_bjbed_a_a3ee288e", True),
        ("bj2p_a_616c0469", True),
        ("bjconsole_b_f042c091", True),
        ("bjbed", True),
        ("member", False),
        ("opencode", False),
        ("bed", False),
        ("bjbedx", False),
        ("zoid6", False),
    ],
)
def test_fixture_role_pattern(name, matches):
    assert bool(cts.FIXTURE_ROLE_RE.match(name)) is matches


@pytest.mark.unit
def test_pristine_is_true_only_when_all_six_checks_pass():
    clean = cts.PristineState(
        roles=[], memberships=[], engine_grants=[], rows=[], tables=[], pgrole_rows=[],
        password_file_present=False,
    )
    assert cts.pristine_report(clean) == []
    dirty = clean._replace(roles=["m_bjbed_a"])
    report = cts.pristine_report(dirty)
    assert report and report[0][0] == "roles"


@pytest.mark.unit
def test_each_check_reports_its_own_group():
    s = cts.PristineState(
        roles=["bjbed_a"], memberships=[("bjbed_a", "opencode")], engine_grants=["m_bjbed_a"],
        rows=["engine.__member:bjbed_a"], tables=["blackjack-bed-2p-1"], pgrole_rows=["m_bjbed_a"],
        password_file_present=True,
    )
    groups = [g for g, _ in cts.pristine_report(s)]
    assert groups == ["roles", "memberships", "engine_grants", "rows", "tables", "pgrole_rows", "password_file"]


@pytest.mark.unit
def test_jam_file_name_is_per_database_and_timestamped():
    name = cts.jam_file_name("zoid6", "20261027093000")
    assert name == "zoid6_bjbed_cleanup_jam_zoid6_20261027093000.sql"


@pytest.mark.unit
def test_jam_file_contains_only_the_remaining_items_and_checks_state_first():
    s = cts.PristineState(
        roles=["m_bjbed_a"], memberships=[("m_bjbed_a", "bed")], engine_grants=["m_bjbed_a"],
        rows=[], tables=[], pgrole_rows=[], password_file_present=False,
    )
    sql = cts.render_jam_sql(s)
    assert "m_bjbed_a" in sql
    assert "m_bjbed_b" not in sql, "items that are already clean must not appear"
    assert "IF EXISTS" in sql or "pg_roles" in sql, "each statement must check state first"
    assert "DROP ROLE" in sql


@pytest.mark.unit
def test_jam_file_is_empty_when_nothing_remains():
    clean = cts.PristineState([], [], [], [], [], [], False)
    assert cts.render_jam_sql(clean).strip() == "" or "nothing to do" in cts.render_jam_sql(clean)


@pytest.mark.unit
def test_live_database_is_refused_without_the_flags():
    with pytest.raises(cts.LiveDatabaseRefused):
        cts.check_target("zoid6", allow_live=False, confirmation=None)
    with pytest.raises(cts.LiveDatabaseRefused):
        cts.check_target("zoid6", allow_live=True, confirmation="yes")
    cts.check_target("zoid6", allow_live=True, confirmation="zoid6")
    cts.check_target("zoid6test", allow_live=False, confirmation=None)


@pytest.mark.unit
def test_module_uses_bbsengine6_database_and_io_not_raw_connections():
    src = Path(cts.__file__).read_text()
    assert "from bbsengine6 import database" in src or "from bbsengine6 import database as" in src
    assert "from bbsengine6 import io" in src
    assert "psycopg.connect" not in src, "use bbsengine6 database connections"
    assert "print(" not in src, "use bbsengine6 io.echo for output"


@pytest.mark.unit
def test_opencode_never_attempts_role_drops_or_engine_revokes():
    # Role drops and engine-schema revokes have never succeeded for opencode; they belong to the jam
    # file. The tool must not issue DROP ROLE, engine.deletepgrole, or an engine-schema REVOKE.
    import ast

    tree = ast.parse(Path(cts.__file__).read_text())
    jam_only = {"render_jam_sql", "render_jam_phases"}
    opencode_fns = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name not in jam_only]
    code = "\n".join(ast.get_source_segment(Path(cts.__file__).read_text(), n) or "" for n in opencode_fns)
    # Only string literals count as statements; prose in docstrings is skipped by the AST walk.
    literals = [n.value for n in ast.walk(ast.parse(code)) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    sql = "\n".join(literals)
    assert "DROP ROLE" not in sql, "opencode must not issue DROP ROLE"
    assert "deletepgrole" not in sql, "opencode must not call engine.deletepgrole"
    assert "REVOKE USAGE ON SCHEMA engine" not in sql, "opencode must not revoke engine grants"


@pytest.mark.unit
def test_membership_revoke_does_not_use_cascade():
    # CASCADE would also remove grants that opencode passed on. The tool must not use it; a
    # membership with dependents is reported for jam to decide.
    import ast

    tree = ast.parse(Path(cts.__file__).read_text())
    # Skip docstrings (the first string statement of each function or module); check everything else.
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                docstrings.add(id(first.value))
    sql = [n.value for n in ast.walk(tree)
           if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings]
    assert not any("CASCADE" in s for s in sql), "the tool must not issue CASCADE"


@pytest.mark.unit
def test_dependent_membership_is_reported_not_forced():
    # A revoke refused for dependent privileges is recorded as refused, with the reason.
    import inspect

    src = inspect.getsource(cts._revoke_own_memberships)
    assert "dependent" in src or "except" in src
    assert "refused" in src, "a refused membership must be reported as refused"


@pytest.mark.unit
def test_jam_file_revokes_onward_grants_before_base_memberships():
    s = cts.PristineState(
        roles=[], memberships=[("bj2p_a_1", "opencode")], engine_grants=[], rows=[],
        tables=[], pgrole_rows=[], password_file_present=False,
    )
    sql = cts.render_jam_sql(s, dependents=[("bj2p_a_1", "bj2p_a_2")])
    dep = sql.index('"bj2p_a_1" FROM "bj2p_a_2"')
    base = sql.index('"bj2p_a_1" FROM "opencode"')
    assert dep < base, "onward grants must be revoked before the base membership"


@pytest.mark.unit
def test_onward_grant_revokes_name_opencode_as_grantor():
    # The 23 onward grants were made by opencode. A plain REVOKE only matches grants made by
    # postgres, so each onward revoke must say GRANTED BY opencode, or it silently does nothing.
    s = cts.PristineState(
        roles=[], memberships=[], engine_grants=[], rows=[],
        tables=[], pgrole_rows=[], password_file_present=False,
    )
    sql = cts.render_jam_sql(s, dependents=[("bj2p_a_1", "bj2p_a_2")])
    assert 'REVOKE "bj2p_a_1" FROM "bj2p_a_2" GRANTED BY "opencode"' in sql


@pytest.mark.unit
def test_role_drops_are_a_separate_phase_after_all_dependencies():
    # Roles are cluster-wide: a drop fails while any database still holds a dependent. The drops
    # must be in their own phase, run once after every database's dependents are cleared.
    s = cts.PristineState(
        roles=["m_bjbed_a", "bjbed_a"], memberships=[("m_bjbed_a", "opencode")],
        engine_grants=["m_bjbed_a"], rows=[], tables=[], pgrole_rows=[], password_file_present=False,
    )
    phase1, phase2 = cts.render_jam_phases(s, dependents=[])
    assert "DROP ROLE" not in phase1, "phase 1 must not drop roles"
    assert "DROP ROLE" in phase2, "phase 2 must drop the roles"
    assert "REVOKE" in phase1 and "REVOKE" not in phase2


@pytest.mark.unit
def test_password_file_is_removed_once_everything_else_is_clean(tmp_path, monkeypatch):
    from unittest.mock import patch

    pw = tmp_path / "bed-fixtures.json"
    pw.write_text("{}")
    monkeypatch.setattr(cts, "PASSWORD_FILE", pw)
    clean_but_file = cts.PristineState([], [], [], [], [], [], True)
    with patch.object(cts, "_catalog_state", return_value=clean_but_file), \
         patch.object(cts, "_delete_rows"), patch.object(cts, "_revoke_own_memberships", return_value=[]), \
         patch.object(cts, "_onward_grants", return_value=[]), \
         patch.object(cts.dbmod, "getpool", return_value=type("P", (), {"close": lambda self: None})()), \
         patch.object(cts.io, "echo"):
        ok = cts.run(object(), database="zoid6test")
    assert ok is True
    assert not pw.exists(), "the password file must be removed once nothing else remains"
