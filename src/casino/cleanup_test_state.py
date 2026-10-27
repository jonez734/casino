"""casino --cleanup-test-state: remove bed test state as far as opencode can, report the rest.

Test state here means the fixture roles (bj2p_*, bjbed_*, bjconsole_* and their m_ forms), their
memberships, engine-schema grants, member, bank, player and table rows, engine.pgrole rows, and the
test password file.

opencode removes what it can: rows, its own memberships, and the password file. It does not attempt
role drops or engine-schema revokes, because those have never succeeded for opencode (DROP ROLE needs
ADMIN OPTION on the target; revokes of zoid6-granted engine privileges are silently ignored). Anything
left is written to a jam file, which only jam can run.

The database is considered pristine only when a read-only check of the catalog passes.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any, List, NamedTuple, Optional, Tuple

from bbsengine6 import database as dbmod
from bbsengine6 import io

FIXTURE_ROLE_RE = re.compile(r"^(m_)?(bj2p|bjbed|bjconsole)(_|$)")
FIXTURE_NAME_RE = re.compile(r"^(bj2p|bjbed|bjconsole)(_|$)")
DEFAULT_DATABASE = "zoid6test"
LIVE_DATABASES = frozenset({"zoid6"})
PASSWORD_FILE = Path(os.path.expanduser("~")) / ".config" / "casino" / "test-data" / "bed-fixtures.json"


class LiveDatabaseRefused(Exception):
    """A live database was named without --allow-live and a matching --confirm."""


class PristineState(NamedTuple):
    roles: List[str]
    memberships: List[Tuple[str, str]]
    engine_grants: List[str]
    rows: List[str]
    tables: List[str]
    pgrole_rows: List[str]
    password_file_present: bool


CHECK_GROUPS = ("roles", "memberships", "engine_grants", "rows", "tables", "pgrole_rows", "password_file")


def check_target(database: str, *, allow_live: bool, confirmation: Optional[str]) -> None:
    if database not in LIVE_DATABASES:
        return
    if not allow_live:
        raise LiveDatabaseRefused(f"{database} is live; pass --allow-live and --confirm {database}")
    if confirmation != database:
        raise LiveDatabaseRefused(f"--confirm must be {database}")


def pristine_report(state: PristineState) -> List[Tuple[str, List[str]]]:
    """Each failing check and what remains for it. Empty when the database is pristine."""
    items = {
        "roles": [r for r in state.roles],
        "memberships": [f"{m} of {r}" for r, m in state.memberships],
        "engine_grants": list(state.engine_grants),
        "rows": list(state.rows),
        "tables": list(state.tables),
        "pgrole_rows": list(state.pgrole_rows),
        "password_file": [str(PASSWORD_FILE)] if state.password_file_present else [],
    }
    return [(group, items[group]) for group in CHECK_GROUPS if items[group]]


def jam_file_name(database: str, stamp: str) -> str:
    return f"zoid6_bjbed_cleanup_jam_{database}_{stamp}.sql"


def render_jam_phases(state: PristineState, dependents: Optional[List[Tuple[str, str]]] = None) -> Tuple[str, str]:
    """Split the jam SQL into two phases.

    Phase 1 (per database): revoke onward grants, base memberships, engine grants, and delete pgrole
    rows. Safe to run in each database in turn.
    Phase 2 (once, after phase 1 in every database): drop the login roles, then the data roles.
    Roles are cluster-wide, so they can only be dropped after every database has let go of them.
    """
    full = render_jam_sql(state, dependents=dependents)
    drops = [line for line in full.splitlines() if "DROP ROLE" in line]
    body = [line for line in full.splitlines() if line not in drops and line not in ("BEGIN;", "COMMIT;")]
    phase1 = "BEGIN;\n" + "\n".join(body) + "\nCOMMIT;\n"
    phase2 = "BEGIN;\n" + "\n".join(drops) + "\nCOMMIT;\n" if drops else "-- no roles to drop\n"
    return phase1, phase2


def render_jam_sql(state: PristineState, dependents: Optional[List[Tuple[str, str]]] = None) -> str:
    """SQL for jam: only the items that remain, each statement checking state first.

    ``dependents`` are memberships granted onward by opencode (role, member). They are revoked before
    the base memberships, so no revoke needs CASCADE and nothing else is removed implicitly.
    """
    lines: List[str] = []
    for role, member in (dependents or []):
        # Granted by opencode: a plain REVOKE only matches grants made by postgres and does nothing here.
        lines.append(
            f'DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_auth_members m JOIN pg_roles g ON g.oid=m.roleid '
            f"JOIN pg_roles u ON u.oid=m.member WHERE g.rolname='{role}' AND u.rolname='{member}' "
            f"AND m.grantor = 'opencode'::regrole) "
            f'THEN REVOKE "{role}" FROM "{member}" GRANTED BY "opencode"; END IF; END $$;'
        )
    for role, member in state.memberships:
        lines.append(
            f'DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_auth_members m JOIN pg_roles g ON g.oid=m.roleid '
            f"JOIN pg_roles u ON u.oid=m.member WHERE g.rolname='{role}' AND u.rolname='{member}') "
            f'THEN REVOKE "{role}" FROM "{member}"; END IF; END $$;'
        )
    for role in state.engine_grants:
        lines.append(
            f'DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_namespace n, unnest(n.nspacl) a '
            f"WHERE n.nspname='engine' AND a::text LIKE '{role}=%') "
            f'THEN REVOKE USAGE ON SCHEMA engine FROM "{role}"; END IF; END $$;'
        )
    for role in state.pgrole_rows:
        lines.append(f"DELETE FROM engine.pgrole WHERE rolname = '{role}';")
    logins = [r for r in state.roles if not r.startswith("m_")]
    datas = [r for r in state.roles if r.startswith("m_")]
    for role in logins + datas:
        lines.append(
            f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{role}') "
            f'THEN DROP ROLE "{role}"; END IF; END $$;'
        )
    if not lines:
        return "-- nothing to do\n"
    return "BEGIN;\n" + "\n".join(lines) + "\nCOMMIT;\n"


def _catalog_state(args: Any, database: str, *, pool: Any) -> PristineState:
    """Read the six checks from the catalog. Read-only."""
    with dbmod.connect(args, pool=pool) as conn, dbmod.cursor(conn) as cur:
        cur.execute("SELECT rolname FROM pg_roles WHERE rolname ~ %s ORDER BY 1", (FIXTURE_ROLE_RE.pattern,))
        roles = [r["rolname"] for r in cur.fetchall()]

        cur.execute(
            "SELECT g.rolname AS role, u.rolname AS member FROM pg_auth_members m "
            "JOIN pg_roles g ON g.oid = m.roleid JOIN pg_roles u ON u.oid = m.member "
            "WHERE g.rolname ~ %s AND u.rolname IN ('opencode', 'bed') ORDER BY 1, 2",
            (FIXTURE_ROLE_RE.pattern,),
        )
        memberships = [(r["role"], r["member"]) for r in cur.fetchall()]

        cur.execute(
            "SELECT DISTINCT split_part(a::text, '=', 1) AS role FROM pg_namespace n, unnest(n.nspacl) a "
            "WHERE n.nspname = 'engine' AND split_part(a::text, '=', 1) ~ %s ORDER BY 1",
            (FIXTURE_ROLE_RE.pattern,),
        )
        engine_grants = [r["role"].strip('"') for r in cur.fetchall()]

        rows: List[str] = []
        cur.execute("SELECT moniker FROM engine.__member WHERE moniker ~ %s", (FIXTURE_NAME_RE.pattern,))
        rows += [f"engine.__member:{r['moniker']}" for r in cur.fetchall()]
        cur.execute("SELECT moniker FROM bank.__account WHERE moniker ~ %s", (FIXTURE_NAME_RE.pattern,))
        rows += [f"bank.__account:{r['moniker']}" for r in cur.fetchall()]
        cur.execute("SELECT moniker FROM casino.__player WHERE moniker ~ %s", (FIXTURE_NAME_RE.pattern,))
        rows += [f"casino.__player:{r['moniker']}" for r in cur.fetchall()]

        cur.execute(
            "SELECT moniker FROM casino.__table WHERE moniker LIKE 'blackjack-bed-%%' "
            "OR moniker LIKE 'blackjack-bed-2p-%%' OR moniker LIKE 'blackjack-%%-2p-%%'"
        )
        tables = [r["moniker"] for r in cur.fetchall()]

        cur.execute("SELECT rolname FROM engine.pgrole WHERE rolname ~ %s", (FIXTURE_ROLE_RE.pattern,))
        pgrole_rows = [r["rolname"] for r in cur.fetchall()]

    return PristineState(
        roles=roles,
        memberships=memberships,
        engine_grants=engine_grants,
        rows=rows,
        tables=tables,
        pgrole_rows=pgrole_rows,
        password_file_present=PASSWORD_FILE.exists(),
    )


def _onward_grants(args: Any, *, pool: Any) -> List[Tuple[str, str]]:
    """Memberships of fixture roles that opencode granted onward. Read-only."""
    with dbmod.connect(args, pool=pool) as conn, dbmod.cursor(conn) as cur:
        cur.execute(
            "SELECT g.rolname AS role, u.rolname AS member FROM pg_auth_members m "
            "JOIN pg_roles g ON g.oid = m.roleid JOIN pg_roles u ON u.oid = m.member "
            "WHERE g.rolname ~ %s AND m.grantor::regrole::text = 'opencode' ORDER BY 1, 2",
            (FIXTURE_ROLE_RE.pattern,),
        )
        return [(r["role"], r["member"]) for r in cur.fetchall()]


def _delete_rows(args: Any, *, pool: Any) -> None:
    """opencode's own deletes: fixture rows, orphan bank accounts, leftover test tables."""
    with dbmod.connect(args, pool=pool) as conn, dbmod.cursor(conn) as cur:
        for sql in (
            "DELETE FROM casino.__bank_player WHERE player_moniker ~ %(p)s",
            "DELETE FROM casino.__player WHERE moniker ~ %(p)s",
            "DELETE FROM bank.__account WHERE moniker ~ %(p)s",
            "DELETE FROM engine.__member WHERE moniker ~ %(p)s",
        ):
            cur.execute(sql, {"p": FIXTURE_NAME_RE.pattern})


def _revoke_own_memberships(args: Any, state: PristineState, *, pool: Any) -> List[Tuple[str, str, str]]:
    """Attempt to revoke opencode's and bed's memberships of fixture roles, each in a savepoint.

    A refused revoke is reported as refused with PostgreSQL's reason. Revokes with dependents are not
    forced with CASCADE, because that would also remove grants opencode passed on; they stay for jam.
    Returns the refusals as (role, member, reason).
    """
    refused: List[Tuple[str, str, str]] = []
    with dbmod.connect(args, pool=pool) as conn, dbmod.cursor(conn) as cur:
        for role, member in state.memberships:
            cur.execute("SAVEPOINT revoke_membership")
            try:
                cur.execute(f'REVOKE "{role}" FROM "{member}"')
                cur.execute("RELEASE SAVEPOINT revoke_membership")
            except Exception as e:
                cur.execute("ROLLBACK TO SAVEPOINT revoke_membership")
                reason = str(e).splitlines()[0] if str(e) else "refused"
                refused.append((role, member, reason))
                io.echo(f"cleanup-test-state: refused: {member} of {role}: {reason}", level="warning")
    return refused


def _database_items(state: PristineState) -> List[Tuple[str, List[str]]]:
    """What still needs jam or opencode in the database. The password file is not a database item."""
    return [item for item in pristine_report(state._replace(password_file_present=False))]


def _remove_password_file() -> None:
    if PASSWORD_FILE.exists():
        PASSWORD_FILE.unlink()
        io.echo("cleanup-test-state: removed " + str(PASSWORD_FILE), level="ok")


def run(args: Any, *, database: str, allow_live: bool = False, confirmation: Optional[str] = None) -> bool:
    """Clean what opencode can, report what remains, write the jam file if anything remains."""
    check_target(database, allow_live=allow_live, confirmation=confirmation)
    pool = dbmod.getpool(args, dbname=database)
    try:
        io.echo(f"cleanup-test-state: {database}: checking", level="ok")
        before = _catalog_state(args, database, pool=pool)
        if not _database_items(before):
            # Nothing in the database remains; the password file is the last item and goes now.
            _remove_password_file()
            io.echo(f"cleanup-test-state: {database} is pristine", level="ok")
            return True

        _delete_rows(args, pool=pool)
        refused = _revoke_own_memberships(args, before, pool=pool)

        # The catalog is the source of truth for what remains.
        state = _catalog_state(args, database, pool=pool)
        if not _database_items(state):
            _remove_password_file()
            io.echo(f"cleanup-test-state: {database} is pristine", level="ok")
            return True
        report = pristine_report(state)

        for group, items in report:
            io.echo(f"cleanup-test-state: {group} remaining ({len(items)}):", level="warning")
            for item in items:
                io.echo(f"  {item}", level="warning")

        stamp = time.strftime("%Y%m%d%H%M%S")
        jam_path = Path.cwd() / jam_file_name(database, stamp)
        sql = render_jam_sql(state, dependents=_onward_grants(args, pool=pool))
        jam_path.write_text(sql, encoding="utf-8")
        io.echo("cleanup-test-state: jam file written: " + str(jam_path), level="warning")
        if refused:
            io.echo(f"cleanup-test-state: {len(refused)} membership revoke(s) refused by PostgreSQL:", level="warning")
            for role, member, reason in refused:
                io.echo("  " + member + " of " + role + ": " + reason, level="warning")
        if state.memberships:
            io.echo(
                "cleanup-test-state: the membership revokes did not remove "
                f"{len(state.memberships)} membership(s); the catalog still lists them, so they are in the jam file.",
                level="warning",
            )
        io.echo("cleanup-test-state: review it, then run it as jam; then re-run this command to confirm",
                level="warning")
        return False
    finally:
        pool.close()
