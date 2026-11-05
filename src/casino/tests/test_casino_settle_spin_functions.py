"""engine.casino_settle_spin settles one slots spin in one transaction.

The op is casino-owned and SECURITY DEFINER. Its grant names bed_zoid6, the daemon's login role,
which is the role casino's slots connections use. These tests pin the contract in source; the
database behaviour is covered by the integration tests gated on CASINO_TEST_DB.
"""

from pathlib import Path

import casino

SQL = Path(casino.__file__).parent / "sql" / "casino_settle_spin_functions.sql"


def _code(text: str) -> str:
    return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("--"))


def _text() -> str:
    return _code(SQL.read_text())


def test_function_is_security_definer_owned_by_zoid6():
    t = _text()
    assert "SECURITY DEFINER" in t
    assert "OWNER TO zoid6" in t


def test_grant_names_the_daemon_login_role_not_bed():
    t = _text()
    assert "REVOKE ALL ON FUNCTION engine.casino_settle_spin(bytea, jsonb) FROM PUBLIC" in t
    assert "GRANT EXECUTE ON FUNCTION engine.casino_settle_spin(bytea, jsonb) TO bed_zoid6" in t
    assert "TO bed;" not in t


def test_actor_comes_from_the_token_row_only():
    t = _text()
    assert "FROM engine.__bed_token t" in t
    assert "t.token_hash = p_token_hash" in t
    # The request never names the player.
    assert "p_args->>'player'" not in t
    assert "p_args->>'moniker'" not in t


def test_net_must_match_payout_minus_bet():
    assert "v_net IS DISTINCT FROM (v_payout - v_bet)" in _text()


def test_overdraft_is_refused_with_a_code_not_raised():
    t = _text()
    assert "v_net < 0 AND v_balance < -v_net" in t
    assert "'insufficient_funds'" in t


def test_money_audit_and_stats_are_written_in_this_one_function():
    t = _text()
    assert "UPDATE bank.__account" in t
    assert "INSERT INTO bank.__transaction" in t
    assert "INSERT INTO casino.__slot_spin" in t
    assert "UPDATE casino.__player" in t


def test_startup_installs_the_settle_op_after_casino_op():
    from casino import startup as casino_startup

    src = Path(casino_startup.__file__).read_text() if hasattr(casino_startup, "__file__") else ""
    main = Path(casino.__file__).parent / "startup" / "main.py"
    text = main.read_text()
    assert "casino_settle_spin_functions.sql" in text
    assert text.index("casino_op_functions.sql") < text.index("casino_settle_spin_functions.sql")
