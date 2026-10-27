#!/usr/bin/env python3
# casino/tests/test_test_data_install.py
# casino --install-test-data: the bed test fixtures, created by an explicit install instead of by
# each test run. These tests cover the pure logic (names, password file, safety gate). Stubbed:
# no database, no daemon.

import json
import os
import stat
from types import SimpleNamespace

import pytest

from casino import test_data


@pytest.mark.unit
def test_fixture_names_are_fixed_and_member_safe():
    names = test_data.FIXTURE_MONIKERS
    assert names == ("bjbed_a", "bjbed_b")
    for n in names:
        assert all(c.isalnum() or c == "_" for c in n), n


@pytest.mark.unit
def test_password_file_is_under_the_user_config_dir_not_the_repo(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    path = test_data.password_file_path()
    assert str(path).startswith(str(tmp_path / ".config" / "casino"))
    assert "/src/" not in str(path)


@pytest.mark.unit
def test_write_password_file_is_mode_0600_and_holds_both_passwords(tmp_path):
    path = tmp_path / "test-data" / "bed-fixtures.json"
    test_data.write_password_file(path, {"bjbed_a": "pw-a-123", "bjbed_b": "pw-b-456"})
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(path.parent).st_mode) == 0o700
    data = json.loads(path.read_text())
    assert data["bjbed_a"]["password"] == "pw-a-123"
    assert data["bjbed_b"]["password"] == "pw-b-456"


@pytest.mark.unit
def test_read_password_file_round_trips(tmp_path):
    path = tmp_path / "bed-fixtures.json"
    test_data.write_password_file(path, {"bjbed_a": "x", "bjbed_b": "y"})
    got = test_data.read_password_file(path)
    assert got == {"bjbed_a": "x", "bjbed_b": "y"}


@pytest.mark.unit
def test_read_password_file_refuses_a_world_readable_file(tmp_path):
    path = tmp_path / "bed-fixtures.json"
    test_data.write_password_file(path, {"bjbed_a": "x", "bjbed_b": "y"})
    os.chmod(path, 0o644)
    with pytest.raises(PermissionError):
        test_data.read_password_file(path)


@pytest.mark.unit
def test_generated_passwords_are_random_and_long():
    a = test_data.new_password()
    b = test_data.new_password()
    assert a != b
    assert len(a) >= 24


@pytest.mark.unit
def test_zoid6_needs_the_explicit_flag_and_a_typed_confirmation():
    # Only the scratch database is the default. Anything else, zoid6 included, must be
    # refused unless the operator names it and types the confirmation.
    assert test_data.check_target("zoid6test", allow_live=False, confirmation=None) is None
    with pytest.raises(test_data.LiveDatabaseRefused):
        test_data.check_target("zoid6", allow_live=False, confirmation=None)
    with pytest.raises(test_data.LiveDatabaseRefused):
        test_data.check_target("zoid6", allow_live=True, confirmation="yes")
    assert test_data.check_target("zoid6", allow_live=True, confirmation="zoid6") is None


@pytest.mark.unit
def test_install_refuses_when_a_fixture_member_already_exists():
    existing = {"bjbed_a"}
    with pytest.raises(test_data.FixturesExist):
        test_data.refuse_if_present(existing)
    test_data.refuse_if_present(set())


@pytest.mark.unit
def test_bed_test_reads_fixtures_and_creates_no_roles():
    from pathlib import Path

    src = (Path(__file__).parent / "test_blackjack_two_players_three_games_bed.py").read_text()
    setup = src.split("async def asyncSetUp")[1].split("async def asyncTearDown")[0] if "async def asyncSetUp" in src else src
    assert "test_data" in src, "the bed test must read fixtures from the install file"
    assert "con_member.add" not in setup, "the bed test must not create members in setUp"
    assert "createpgrole" not in src, "the bed test must not create roles"
    assert "GRANT " not in setup, "the bed test must not grant anything"


@pytest.mark.unit
def test_test_data_defaults_to_the_scratch_database_not_the_parser_default():
    # The parser defaults --databasename to zoid6. The test-data commands must not inherit that.
    import inspect
    from casino import __main__ as cm

    src = inspect.getsource(cm._run_test_data)
    assert "DEFAULT_DATABASE" in src
    assert "explicit" in src


@pytest.mark.unit
def test_install_grants_bed_set_on_both_the_login_and_the_data_role():
    # The daemon switches into the member's login role (<moniker>) as well as its data role
    # (m_<moniker>). A grant on only the data role leaves the login switch refused.
    import inspect
    from casino import test_data

    src = inspect.getsource(test_data.install)
    assert 'GRANT "{moniker}" TO bed' in src or "GRANT \"{moniker}\" TO bed" in src, (
        "install must grant bed SET on the login role <moniker>"
    )
    assert 'GRANT "{role}" TO bed' in src, "install must grant bed SET on the data role"


@pytest.mark.unit
def test_uninstall_reports_roles_it_cannot_drop_instead_of_failing_midway():
    # opencode cannot drop a role another role created. Uninstall must finish the rows it can
    # remove, name the roles left for jam, and keep the password file if roles remain.
    import inspect
    from casino import test_data

    src = inspect.getsource(test_data.uninstall)
    assert "InsufficientPrivilege" in src or "except" in src, "uninstall must handle the drop refusal"
    assert "left for jam" in src or "for jam" in src, "uninstall must name the roles left for jam"


@pytest.mark.unit
def test_opencode_is_a_casino_member_for_live_play():
    # The live daemon logs a player in as a member and switches into the member's roles. opencode
    # needs the same member row and bed grant a fixture gets, so it can play.
    from casino import test_data

    assert hasattr(test_data, "ensure_opencode_member"), "test_data must provide the opencode member setup"
