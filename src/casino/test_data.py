"""Bed test fixtures, installed explicitly (``casino --install-test-data``).

The bed-daemon tests need two members with known credentials. Creating them inside every test run
leaked roles and grants on the shared database, so they are installed once and removed on request.

Passwords are random per install. They are written only to a mode-0600 file under the operator's
config directory, never printed or committed.
"""

from __future__ import annotations

import json
import os
import secrets
import stat
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

FIXTURE_MONIKERS = ("bjbed_a", "bjbed_b")
DEFAULT_DATABASE = "zoid6test"
LIVE_DATABASES = frozenset({"zoid6"})


class LiveDatabaseRefused(Exception):
    """Raised when the install targets a live database without the explicit flag and confirmation."""


class FixturesExist(Exception):
    """Raised when a fixture member already exists, so the install would overwrite it."""


def password_file_path() -> Path:
    """Where the fixture passwords live: the operator's config directory, outside the repo."""
    return Path(os.path.expanduser("~")) / ".config" / "casino" / "test-data" / "bed-fixtures.json"


def new_password() -> str:
    """A random password that is never shown or stored anywhere but the 0600 file."""
    return secrets.token_urlsafe(24)


def check_target(database: str, *, allow_live: bool, confirmation: Optional[str]) -> None:
    """Refuse a live database unless the operator named it and typed it as the confirmation.

    The scratch database needs nothing extra. Any database in LIVE_DATABASES needs ``allow_live``
    and a ``confirmation`` equal to its name.
    """
    if database not in LIVE_DATABASES:
        return None
    if not allow_live:
        raise LiveDatabaseRefused(
            f"{database} is a live database; pass --database {database} with --allow-live"
        )
    if confirmation != database:
        raise LiveDatabaseRefused(f"type the database name ({database}) to confirm")
    return None


def refuse_if_present(existing: Iterable[str]) -> None:
    """Refuse the install when any fixture member already exists."""
    present = sorted(set(existing) & set(FIXTURE_MONIKERS))
    if present:
        raise FixturesExist(f"fixture members already exist: {', '.join(present)}; uninstall first")


def write_password_file(path: Path, passwords: Dict[str, str]) -> None:
    """Write the fixture passwords with mode 0600 in a 0700 directory. Replaces any old file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    payload: Dict[str, Dict[str, Any]] = {m: {"password": p} for m, p in passwords.items()}
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)
    os.chmod(path, 0o600)


def read_password_file(path: Path) -> Dict[str, str]:
    """Read the fixture passwords. Refuses a file that anyone besides the owner can read."""
    path = Path(path)
    mode = stat.S_IMODE(os.stat(path).st_mode)
    if mode & 0o077:
        raise PermissionError(f"{path} is readable by others (mode {oct(mode)}); expected 0600")
    data = json.loads(path.read_text(encoding="utf-8"))
    return {m: entry["password"] for m, entry in data.items()}


# ---------------------------------------------------------------------------
# Database side. Creates and removes the fixtures through the engine's own paths.
# ---------------------------------------------------------------------------


def _member_record(moniker: str, password: str) -> Dict[str, Any]:
    """The member record ``bbsengine6.console.member.add`` takes, for one fixture member."""
    return {
        "moniker": moniker,
        "loginid": moniker,
        "email": f"{moniker}@test.local",
        "password": password,
        "credits": 100000,
        "ui": ["term"],
        "attrs": {},
        "flags": {
            "APPROVED": {"value": True, "description": "Approved"},
            "SYSOP": {"value": False, "description": "Sysop"},
        },
    }


def install(args: Any, *, database: str, allow_live: bool = False, confirmation: Optional[str] = None) -> bool:
    """Create the fixture members, roles, bed grants and password file in ``database``.

    Refuses a live database unless the operator named it and confirmed (see ``check_target``), and
    refuses when a fixture member already exists.
    """
    from bbsengine6 import database as dbmod
    from bbsengine6 import io
    from bbsengine6 import pgrole
    from bbsengine6.console import member as con_member
    from unittest.mock import patch

    check_target(database, allow_live=allow_live, confirmation=confirmation)

    pool = dbmod.getpool(args, dbname=database)
    try:
        with dbmod.connect(args, pool=pool) as conn, dbmod.cursor(conn) as cur:
            cur.execute("SELECT moniker FROM engine.__member WHERE moniker = ANY(%s)", (list(FIXTURE_MONIKERS),))
            refuse_if_present([r["moniker"] for r in cur.fetchall()])

        passwords = {m: new_password() for m in FIXTURE_MONIKERS}
        for moniker in FIXTURE_MONIKERS:
            record = _member_record(moniker, passwords[moniker])
            with patch.object(con_member, "_edit") as edit, \
                 patch("bbsengine6.io.inputboolean", return_value=True):
                edit.return_value = record
                if con_member.add(args, pool=pool) is not True:
                    io.echo(f"install-test-data: member.add failed for {moniker}", level="error")
                    return False
            with dbmod.connect(args, pool=pool) as conn, dbmod.cursor(conn) as cur:
                cur.execute("INSERT INTO bank.__account (moniker, balance) VALUES (%s, 0) ON CONFLICT (moniker) DO NOTHING", (moniker,))
                cur.execute(
                    "INSERT INTO casino.__player (membermoniker, moniker, location, attrs) "
                    "VALUES (%s, %s, 'casino', '{\"is_bot\": false}') ON CONFLICT (moniker) DO NOTHING",
                    (moniker, moniker),
                )
            # The bed daemon's login needs SET on this member's data role to act for it.
            pgrole.ensure_login_role(args, moniker, pool=pool)
            role = pgrole.role_name_for(moniker)
            # The daemon switches into the login role (<moniker>) and the data role (m_<moniker>).
            with dbmod.connect(args, pool=pool) as conn, dbmod.cursor(conn) as cur:
                cur.execute(f'GRANT "{moniker}" TO bed WITH SET TRUE, INHERIT FALSE')
                cur.execute(f'GRANT "{role}" TO bed WITH SET TRUE, INHERIT FALSE')
            io.echo(f"install-test-data: created {moniker}", level="ok")

        write_password_file(password_file_path(), passwords)
        io.echo(f"install-test-data: passwords written to {password_file_path()} (mode 0600)".replace("{", "(").replace("}", ")"), level="ok")
        return True
    finally:
        pool.close()


def uninstall(args: Any, *, database: str, allow_live: bool = False, confirmation: Optional[str] = None) -> bool:
    """Remove the fixtures: bed grants, engine role paths, member rows, and the password file.

    A role opencode cannot drop is recorded and left for jam. Each step runs under its own savepoint,
    so one refusal does not abort the rest of the removal.
    """
    from bbsengine6 import database as dbmod
    from bbsengine6 import io
    from bbsengine6 import pgrole

    check_target(database, allow_live=allow_live, confirmation=confirmation)

    pool = dbmod.getpool(args, dbname=database)
    leftover_roles: list[str] = []
    try:
        for moniker in FIXTURE_MONIKERS:
            role = pgrole.role_name_for(moniker)
            with dbmod.connect(args, pool=pool) as conn, dbmod.cursor(conn) as cur:
                for name in (moniker, role):
                    cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (name,))
                    if cur.fetchone() is not None:
                        cur.execute("SAVEPOINT grant_revoke")
                        try:
                            cur.execute(f'REVOKE "{name}" FROM bed')
                            cur.execute("RELEASE SAVEPOINT grant_revoke")
                        except Exception:
                            cur.execute("ROLLBACK TO SAVEPOINT grant_revoke")
                            leftover_roles.append(name)

                # Drop the data role through the engine path, under its own savepoint.
                cur.execute("SAVEPOINT drop_data_role")
                try:
                    cur.execute("SELECT engine.deletepgrole(%s)", (role,))
                    cur.execute("RELEASE SAVEPOINT drop_data_role")
                except Exception:
                    cur.execute("ROLLBACK TO SAVEPOINT drop_data_role")
                    leftover_roles.append(role)

                # Drop the login role, under its own savepoint. opencode cannot drop a role another
                # role created; jam removes it.
                cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (moniker,))
                if cur.fetchone() is not None:
                    cur.execute("SAVEPOINT drop_login_role")
                    try:
                        cur.execute(f'DROP ROLE "{moniker}"')
                        cur.execute("RELEASE SAVEPOINT drop_login_role")
                    except Exception:
                        cur.execute("ROLLBACK TO SAVEPOINT drop_login_role")
                        leftover_roles.append(moniker)

                cur.execute("DELETE FROM casino.__bank_player WHERE player_moniker = %s", (moniker,))
                cur.execute("DELETE FROM casino.__player WHERE moniker = %s", (moniker,))
                cur.execute("DELETE FROM bank.__account WHERE moniker = %s", (moniker,))
                cur.execute("DELETE FROM engine.__member WHERE moniker = %s", (moniker,))
            io.echo(f"install-test-data: removed {moniker}", level="ok")

        if leftover_roles:
            io.echo(
                "install-test-data: roles left for jam to drop: " + ", ".join(sorted(set(leftover_roles))),
                level="warning",
            )
            # Keep the password file while roles remain, so a re-install can still read the names.
            return False
        path = password_file_path()
        if path.exists():
            path.unlink()
        return True
    finally:
        pool.close()
