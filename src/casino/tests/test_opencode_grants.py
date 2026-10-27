#!/usr/bin/env python3
# casino/tests/test_opencode_grants.py
# casino --install-opencode / --uninstall-opencode: opencode's own access for the bed test flows.
# Pure logic only (declared list, record of newly made grants, revoke-only-recorded, jam commands,
# live-database gate). No database.

import json
from pathlib import Path

import pytest

from casino import opencode_grants as og


@pytest.mark.unit
def test_declared_grants_are_the_minimum_set_and_nothing_privileged():
    grants = og.DECLARED_GRANTS
    assert grants, "the grant list must not be empty"
    for g in grants:
        assert g.privilege in {"SELECT", "INSERT", "UPDATE", "DELETE", "USAGE"}, g
        assert g.target.split(".")[0] in {"bank", "casino", "engine"}, g
    # No grant names a privileged role, and no grant is a role or database privilege.
    privileges = {g.privilege for g in grants}
    assert privileges <= {"SELECT", "INSERT", "UPDATE", "DELETE", "USAGE"}
    targets = {g.target for g in grants}
    assert not any(t in ("sysop", "term", "member", "bed", "zoid6") for t in targets)


@pytest.mark.unit
def test_declared_grants_include_the_engine_member_path_tables():
    targets = {g.target for g in og.DECLARED_GRANTS}
    for t in ("engine.__member", "engine.pgrole", "engine.map_member_flag", "bank.__transaction", "bank.__account"):
        assert t in targets, t


@pytest.mark.unit
def test_record_keeps_only_newly_made_grants(tmp_path):
    rec = tmp_path / "opencode-grants.json"
    og.write_record(rec, "zoid6test", [("INSERT", "bank.__account"), ("SELECT", "bank.__account")])
    data = json.loads(rec.read_text())
    assert data["zoid6test"] == [["INSERT", "bank.__account"], ["SELECT", "bank.__account"]]


@pytest.mark.unit
def test_record_file_is_mode_0600(tmp_path):
    import os
    import stat

    rec = tmp_path / "opencode-grants.json"
    og.write_record(rec, "zoid6test", [("SELECT", "bank.__account")])
    assert stat.S_IMODE(os.stat(rec).st_mode) == 0o600


@pytest.mark.unit
def test_uninstall_revokes_only_recorded_grants(tmp_path):
    rec = tmp_path / "opencode-grants.json"
    og.write_record(rec, "zoid6test", [("SELECT", "bank.__account")])
    plan = og.revoke_plan(rec, "zoid6test")
    assert plan == [("SELECT", "bank.__account")]
    # A grant not in the record is never in the plan.
    assert ("INSERT", "casino.__table") not in plan


@pytest.mark.unit
def test_uninstall_deletes_the_record_once_every_recorded_grant_is_revoked(tmp_path):
    rec = tmp_path / "opencode-grants.json"
    og.write_record(rec, "zoid6test", [("SELECT", "bank.__account")])
    og.clear_record(rec, "zoid6test", remaining=[])
    assert not rec.exists()


@pytest.mark.unit
def test_uninstall_keeps_entries_that_could_not_be_revoked(tmp_path):
    rec = tmp_path / "opencode-grants.json"
    og.write_record(rec, "zoid6test", [("SELECT", "bank.__account"), ("INSERT", "bank.__account")])
    og.clear_record(rec, "zoid6test", remaining=[("INSERT", "bank.__account")])
    data = json.loads(rec.read_text())
    assert data["zoid6test"] == [["INSERT", "bank.__account"]]


@pytest.mark.unit
def test_refused_grant_produces_a_jam_command():
    cmd = og.jam_grant_command("INSERT", "engine.pgrole", "opencode")
    assert cmd == 'GRANT INSERT ON engine.pgrole TO "opencode";'
    rcmd = og.jam_revoke_command("INSERT", "engine.pgrole", "opencode")
    assert rcmd == 'REVOKE INSERT ON engine.pgrole FROM "opencode";'


@pytest.mark.unit
def test_live_database_is_refused_without_the_flags():
    with pytest.raises(og.LiveDatabaseRefused):
        og.check_target("zoid6", allow_live=False, confirmation=None)
    with pytest.raises(og.LiveDatabaseRefused):
        og.check_target("zoid6", allow_live=True, confirmation="no")
    og.check_target("zoid6", allow_live=True, confirmation="zoid6")
    og.check_target("zoid6test", allow_live=False, confirmation=None)


@pytest.mark.unit
def test_module_uses_bbsengine6_database_and_io():
    src = Path(og.__file__).read_text()
    assert "from bbsengine6 import database" in src
    assert "from bbsengine6 import io" in src
    assert "psycopg.connect" not in src


@pytest.mark.unit
def test_install_with_nothing_newly_granted_records_nothing(tmp_path):
    # When every grant already held, the tool made none and must not record an empty entry.
    rec = tmp_path / "opencode-grants.json"
    og.write_record(rec, "zoid6test", [("SELECT", "bank.__account")])
    og.clear_record(rec, "zoid6test", remaining=[])
    assert not rec.exists() or "zoid6test" not in json.loads(rec.read_text())
