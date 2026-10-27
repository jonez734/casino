"""casino --install-opencode / --uninstall-opencode: opencode's own access for the bed test flows.

The install grants opencode the minimum table and sequence rights the bed-test fixtures and the test
flows need, and records only the grants it newly made. The uninstall revokes only those recorded
grants. A grant that cannot be made or revoked is reported with the exact jam command for it, and
is not recorded as done.

Grants on zoid6-owned tables can only be made or revoked by zoid6 or jam, so most refusals on zoid6
produce a jam command. On zoid6test opencode may manage its own grants; the install verifies each one.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

from bbsengine6 import database as dbmod
from bbsengine6 import io

ROLE = "opencode"
DEFAULT_DATABASE = "zoid6test"
LIVE_DATABASES = frozenset({"zoid6"})
RECORD_FILE = Path(os.path.expanduser("~")) / ".config" / "casino" / "opencode-grants.json"


class LiveDatabaseRefused(Exception):
    """A live database was named without --allow-live and a matching --confirm."""


class Grant(NamedTuple):
    privilege: str
    target: str  # schema.object; a sequence uses the USAGE privilege on its name

    @property
    def is_sequence(self) -> bool:
        return self.privilege == "USAGE"


# The minimum set: the 14 objects of the bed-fixture grants, the 5 engine member-path tables, and
# bank.__transaction (written when a member's bank account is opened). Nothing for sysop, term,
# member, or superuser.
_TABLE_RIGHTS = ("SELECT", "INSERT", "UPDATE", "DELETE")
_TABLES = (
    "bank.__account",
    "bank.__transaction",
    "casino.__table",
    "casino.map_cardtable_player",
    "casino.__game",
    "casino.__hand",
    "casino.__betlog",
    "casino.__bank_table",
    "casino.__bank_player",
    "casino.__player",
    "engine.__member",
    "engine.map_member_flag",
    "engine.member_flag",
    "engine.pgrole",
    "engine.__message_group",
    "engine.__message_group_member",
)
_SEQUENCES = (
    "bank.__account_id_seq",
    "bank.__transaction_id_seq",
    "casino.__game_id_seq",
    "casino.__hand_id_seq",
    "casino.__betlog_id_seq",
)

DECLARED_GRANTS: Tuple[Grant, ...] = tuple(
    [Grant(p, t) for t in _TABLES for p in _TABLE_RIGHTS]
    + [Grant("USAGE", s) for s in _SEQUENCES]
)


def check_target(database: str, *, allow_live: bool, confirmation: Optional[str]) -> None:
    if database not in LIVE_DATABASES:
        return
    if not allow_live:
        raise LiveDatabaseRefused(f"{database} is live; pass --allow-live and --confirm {database}")
    if confirmation != database:
        raise LiveDatabaseRefused(f"--confirm must be {database}")


def _record_load(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _record_save(path: Path, data: Dict[str, Any]) -> None:
    path = Path(path)
    if not data:
        if path.exists():
            path.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.chmod(path, 0o600)


def write_record(path: Path, database: str, made: List[Tuple[str, str]]) -> None:
    """Record the grants this tool newly made, for one database."""
    data = _record_load(path)
    data[database] = [[p, t] for p, t in made]
    _record_save(path, data)


def revoke_plan(path: Path, database: str) -> List[Tuple[str, str]]:
    """The grants uninstall may revoke: only those recorded for this database."""
    return [(p, t) for p, t in _record_load(path).get(database, [])]


def clear_record(path: Path, database: str, *, remaining: List[Tuple[str, str]]) -> None:
    """Keep only the grants that could not be revoked; drop the database entry when none remain."""
    data = _record_load(path)
    if remaining:
        data[database] = [[p, t] for p, t in remaining]
    else:
        data.pop(database, None)
    _record_save(path, data)


def jam_grant_command(privilege: str, target: str, role: str) -> str:
    if privilege == "USAGE":
        return f'GRANT USAGE ON SEQUENCE {target} TO "{role}";'
    return f'GRANT {privilege} ON {target} TO "{role}";'


def jam_revoke_command(privilege: str, target: str, role: str) -> str:
    if privilege == "USAGE":
        return f'REVOKE USAGE ON SEQUENCE {target} FROM "{role}";'
    return f'REVOKE {privilege} ON {target} FROM "{role}";'


def _check(cur: Any, grant: Grant) -> bool:
    if grant.is_sequence:
        cur.execute("SELECT has_sequence_privilege(%s, %s, 'USAGE') AS ok", (ROLE, grant.target))
    else:
        cur.execute("SELECT has_table_privilege(%s, %s, %s) AS ok", (ROLE, grant.target, grant.privilege))
    row = cur.fetchone()
    return bool(row["ok"])


def install(args: Any, *, database: str, allow_live: bool = False, confirmation: Optional[str] = None,
            record_path: Path = RECORD_FILE) -> bool:
    """Grant opencode the declared rights, verify each, and record only the grants newly made."""
    check_target(database, allow_live=allow_live, confirmation=confirmation)
    pool = dbmod.getpool(args, dbname=database)
    made: List[Tuple[str, str]] = []
    refused: List[Tuple[str, str, str]] = []
    try:
        with dbmod.connect(args, pool=pool) as conn, dbmod.cursor(conn) as cur:
            for grant in DECLARED_GRANTS:
                if _check(cur, grant):
                    continue  # already held; not ours to record or revoke
                cur.execute("SAVEPOINT grant_one")
                try:
                    cur.execute(jam_grant_command(grant.privilege, grant.target, ROLE).rstrip(";"))
                    cur.execute("RELEASE SAVEPOINT grant_one")
                except Exception as e:
                    cur.execute("ROLLBACK TO SAVEPOINT grant_one")
                    refused.append((grant.privilege, grant.target, str(e).splitlines()[0]))
                    continue
                if _check(cur, grant):
                    made.append((grant.privilege, grant.target))
                else:
                    refused.append((grant.privilege, grant.target, "grant did not take effect"))
        if made:
            write_record(record_path, database, made)
        else:
            clear_record(record_path, database, remaining=[])
        if made:
            io.echo(f"opencode-grants: {database}: {len(made)} granted and recorded", level="ok")
        else:
            io.echo(f"opencode-grants: {database}: all declared grants already held; none recorded", level="ok")
        if refused:
            io.echo(f"opencode-grants: {database}: {len(refused)} refused; for jam:", level="warning")
            for p, t, reason in refused:
                io.echo("  " + reason, level="warning")
                io.echo("  " + jam_grant_command(p, t, ROLE), level="warning")
            return False
        return True
    finally:
        pool.close()


def uninstall(args: Any, *, database: str, allow_live: bool = False, confirmation: Optional[str] = None,
              record_path: Path = RECORD_FILE) -> bool:
    """Revoke only the recorded grants. Keep any that cannot be revoked, and print the jam command."""
    check_target(database, allow_live=allow_live, confirmation=confirmation)
    plan = revoke_plan(record_path, database)
    if not plan:
        io.echo(f"opencode-grants: {database}: nothing recorded to revoke", level="ok")
        return True
    pool = dbmod.getpool(args, dbname=database)
    remaining: List[Tuple[str, str]] = []
    try:
        with dbmod.connect(args, pool=pool) as conn, dbmod.cursor(conn) as cur:
            for privilege, target in plan:
                cur.execute("SAVEPOINT revoke_one")
                try:
                    cur.execute(jam_revoke_command(privilege, target, ROLE).rstrip(";"))
                    cur.execute("RELEASE SAVEPOINT revoke_one")
                except Exception as e:
                    cur.execute("ROLLBACK TO SAVEPOINT revoke_one")
                    remaining.append((privilege, target))
                    io.echo(f"opencode-grants: refused: {privilege} {target}: {str(e).splitlines()[0]}", level="warning")
                    continue
                grant = Grant(privilege, target)
                if _check(cur, grant):
                    # The revoke did nothing (for example, zoid6 made the grant); keep the record.
                    remaining.append((privilege, target))
        clear_record(record_path, database, remaining=remaining)
        if remaining:
            io.echo(f"opencode-grants: {database}: {len(remaining)} still held; for jam:", level="warning")
            for p, t in remaining:
                io.echo("  " + jam_revoke_command(p, t, ROLE), level="warning")
            return False
        io.echo(f"opencode-grants: {database}: all recorded grants revoked", level="ok")
        return True
    finally:
        pool.close()
