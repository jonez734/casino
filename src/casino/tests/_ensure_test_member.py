"""Audit-gated member provisioning for casino test fixtures.

Provisions an ``engine.__member`` row but only overwrites the password
column when the existing password is unhealthy or absent. Composes with
the ``chk_member_password_bcrypt`` CHECK constraint installed at every
``bbsengine6.startup`` and with ``bbsengine6.member.audit_password_hash``,
which exposes the column's structural flags as a ``PasswordHashAudit``
namedtuple.

Behavior matrix:

- Fresh DB (zoid6test): the row does not exist; the INSERT runs and
  ``setpassword`` runs, writing ``crypt('test', gen_salt('bf'))``.
- Dev DB (zoid6) where the operator already set their own bcrypt
  password on the fixture moniker: ``audit_password_hash`` reports
  ``is_bcrypt=True`` and ``length_ok=True``; the INSERT runs (credits,
  loginid, email reset, which is the fixture contract) and
  ``setpassword`` is skipped, preserving the operator's credentials.
- Dev DB (zoid6) where the row exists with no password yet: the INSERT
  runs and ``setpassword`` runs, since the test needs a usable
  credential.
"""
from __future__ import annotations


def ensure_test_member(
    args,
    moniker: str,
    plaintext: str,
    *,
    pool,
    email: str | None = None,
    credits: int = 100000,
) -> None:
    from bbsengine6 import database
    from bbsengine6.member import lib as libmember

    audit = libmember.audit_password_hash(args, moniker, pool=pool)
    password_already_healthy = audit.is_bcrypt and audit.length_ok

    with database.connect(args, pool=pool) as conn, database.cursor(conn) as cur:
        cur.execute(
            "INSERT INTO engine.__member "
            "(moniker, loginid, email, credits) "
            "VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (moniker) DO UPDATE SET "
            "loginid = EXCLUDED.loginid, "
            "email = EXCLUDED.email, "
            "credits = EXCLUDED.credits",
            (moniker, moniker, email or f"{moniker}@test.local", credits),
        )

    if password_already_healthy:
        return

    libmember.setpassword(args, plaintext, moniker, pool=pool)
