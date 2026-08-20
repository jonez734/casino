"""
Ensure the ``casino`` schema is owned by the dedicated ``zoid6`` role.

This module mirrors the ``engine`` schema block in
``bbsengine6.backend.checkengine`` (``checkengine.py:77-133``), but
scoped to the casino project's own schema. It exists because the
SECURITY DEFINER helper ``public.manage_schema_priv`` — which
``casino.startup.main`` calls to grant schema usage on the
``casino`` schema to ``web``, ``term``, ``sysop``, ``opencode`` —
is owned by ``zoid6`` (a ``NOSUPERUSER`` dedicated owner role
created by ``bbsengine6.backend.checkzoid6role``). A NOSUPERUSER
role can only ``GRANT`` on objects it owns, so the ``casino``
schema must also be owned by ``zoid6`` for those grants to
succeed.

Without this module, a freshly bootstrapped database that runs
``bbsengine6.startup`` (which assigns ownership of the helpers to
``zoid6``) followed by ``casino.startup.main`` fails with::

    psycopg.errors.InsufficientPrivilege:
    permission denied for schema casino

because ``casino`` was created with the bootstrap principal as
owner.

The module also runs the owner-gate from ``checkengine.py:45-75``
against the five SECURITY DEFINER helpers, so it refuses to
continue if any of them is owned by a role outside the hard-coded
allow-list ``("zoid6", "postgres")``. This mirrors the runtime
guard the bbsengine6 backend enforces.

Idempotent. The ``casino`` schema is created (fresh installs) or
reassigned (BC upgrades) to ``zoid6``; on subsequent runs with the
correct owner already in place, this is a no-op.
"""

from bbsengine6 import database, io

SCHEMA_NAME = "casino"
TARGET_ROLE = "zoid6"
ACCEPTABLE_HELPER_OWNERS = ("zoid6", "postgres")

# Mirrors the loop in ``bbsengine6.backend.checkengine``. Keep in
# lock-step; if a helper is added there, add it here so the gate
# covers it.
HELPERS = (
    "public.manage_schema_priv",
    "public.manage_database_priv",
    "public.manage_role_privs",
    "public.manage_secondary_role",
    "public.get_role_privs",
)


def init(args, **kwargs):
    return True


def buildargs(args, **kwargs):
    return None


def access(args, op, **kwargs):
    return True


def main(args, **kwargs):
    """Ensure ``casino`` schema exists and is owned by ``zoid6``.

    Runs after citext is installed and before ``casino.sql.schema.sql``
    is imported. Returns ``True`` on success, ``False`` on any DB
    error.
    """
    failcount = 0
    conn = kwargs.get("conn")

    # --- SECURITY DEFINER owner gate ---
    # Mirror of ``checkengine.py:45-75``. Refuse to call any helper
    # owned by a role outside the hard-coded allow-list; if the
    # helper is not yet installed, skip (checkfunctions in stage 1
    # is responsible for installing it).
    for secdef_fn in HELPERS:
        if not database.functionexists(args, secdef_fn, conn=conn):
            continue
        if not database.verify_function_owner(
            args, secdef_fn, ACCEPTABLE_HELPER_OWNERS, conn=conn
        ):
            io.echo(
                f"checkcasino: refusing to use {secdef_fn} "
                f"(owner mismatch); see error above",
                level="error",
            )
            return False

    # --- casino schema ---
    # Must be owned by ``zoid6`` so that the SECURITY DEFINER helper
    # ``manage_schema_priv`` (also owned by ``zoid6``) can issue
    # GRANT statements on it. ``zoid6`` is NOSUPERUSER and can only
    # GRANT on objects it owns. Without this, every grant in
    # ``casino.startup.main`` would fail with
    # ``permission denied for schema casino`` once the helpers are
    # owned by ``zoid6``.
    io.echo(
        f"{{var:labelcolor}}schema {{var:valuecolor}}{SCHEMA_NAME}"
        f"{{var:labelcolor}}: ",
        end="",
    )

    if database.schemaexists(args, SCHEMA_NAME, conn=conn) is False:
        io.echo("create ", end="")
        # ``database.createschema`` does not accept an owner kwarg,
        # so issue the DDL directly so the new schema is owned by
        # ``zoid6`` from the start
        # (``CREATE SCHEMA ... AUTHORIZATION zoid6``).
        try:
            with database.cursor(conn=conn) as cur:
                cur.execute(
                    f"CREATE SCHEMA {SCHEMA_NAME} "
                    f"AUTHORIZATION {TARGET_ROLE}"
                )
        except Exception as e:
            io.echo("{var:level.error}fail {/all}", level="error")
            io.echo(f"  {e}", level="error")
            return False
        io.echo("{level.ok}  ok  {/all}")
    else:
        # BC: an existing casino schema may be owned by the previous
        # bootstrap principal (e.g. opencode). Reassign to ``zoid6``
        # so the SECDEF helper grants below can succeed.
        try:
            with database.cursor(conn=conn) as cur:
                cur.execute(
                    "SELECT pg_catalog.pg_get_userbyid(nspowner) AS owner "
                    "FROM pg_namespace WHERE nspname = %s",
                    (SCHEMA_NAME,),
                )
                row = cur.fetchone()
                # ``database.cursor`` returns dict rows by default;
                # handle either shape defensively.
                if row is None:
                    current_owner = None
                elif isinstance(row, dict):
                    current_owner = row.get("owner")
                else:
                    current_owner = row[0]
                if current_owner and current_owner != TARGET_ROLE:
                    cur.execute(
                        f"ALTER SCHEMA {SCHEMA_NAME} "
                        f"OWNER TO {TARGET_ROLE}"
                    )
                    io.echo(
                        f"{{level.ok}}ok{{/all}} (reassigned from "
                        f"'{current_owner}' to '{TARGET_ROLE}')"
                    )
                else:
                    io.echo("{level.ok}  ok  {/all}")
        except Exception as e:
            io.echo("{var:level.error}fail {/all}", level="error")
            io.echo(f"  {e}", level="error")
            return False

    return failcount == 0
