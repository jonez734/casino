-- drop-casino-test-roles.sql
--
-- Removes the per-test roles that the casino test fixtures create. Two families:
--
--   bjconsole_<id>   login role     and   m_bjconsole_<id>  data role
--   bj2p_<x>_<id>    login role     and   m_bj2p_<x>_<id>   data role
--
-- Only roles whose names match one of those patterns are touched. The shared roles they are
-- members of (bed, bed_zoid6, member, opencode, ...) are never dropped or altered.
--
-- Postgres will not drop a role that still holds privileges or memberships, so the script:
--   1. revokes the privileges these roles hold on schemas and tables;
--   2. revokes their memberships, in both directions;
--   3. drops each role.
-- A role that still cannot be dropped is reported and skipped; the rest are still removed.
--
-- Idempotent: a second run finds nothing to do and says so.
--
-- Run as jam (superuser) against the test database only:
--
--   psql -U jam -d zoid6test -v ON_ERROR_STOP=1 -f scripts/drop-casino-test-roles.sql

\set ON_ERROR_STOP on

-- One transaction: the temporary role list lives across every step, and any error rolls the
-- whole run back, so a failed run leaves the database as it found it.
begin;

-- Guard: only the test database.
do $$
begin
    if current_database() <> 'zoid6test' then
        raise exception 'drop-casino-test-roles: refusing to run against %, only zoid6test',
            current_database();
    end if;
end
$$;

-- The set of per-test roles, as a temporary table so each step reads the same list.
create temporary table _casino_test_roles as
select r.oid, r.rolname
from pg_roles r
where r.rolname ~ '^(m_)?bjconsole(_[a-z0-9]+)?_[0-9a-f]{8}$'
   or r.rolname ~ '^(m_)?bjconsole$'
   or r.rolname ~ '^(m_)?bjconsole_[ab]$'
   or r.rolname ~ '^(m_)?bj2p_[ab]_[0-9a-f]{8}$'
   or r.rolname ~ '^(m_)?bj2p_[ab]$';

do $$
declare
    n integer;
begin
    select count(*) into n from _casino_test_roles;
    if n = 0 then
        raise notice 'drop-casino-test-roles: no per-test roles present; nothing to do.';
    else
        raise notice 'drop-casino-test-roles: % per-test role(s) to remove.', n;
    end if;
end
$$;

-- 1. Privileges on schemas. A USAGE grant to a per-test role blocks its drop.
do $$
declare
    r record;
    g record;
begin
    for g in
        select n.nspname as schema_name, t.rolname as grantee
        from pg_namespace n
        cross join _casino_test_roles t
        where has_schema_privilege(t.oid, n.oid, 'usage')
          and n.nspname not in ('pg_catalog', 'information_schema')
          and n.nspname not like 'pg_toast%'
    loop
        execute format('revoke usage on schema %I from %I', g.schema_name, g.grantee);
    end loop;
end
$$;

-- 2. Privileges on tables and views. Revoke everything a per-test role was granted.
do $$
declare
    g record;
begin
    for g in
        select c.oid::regclass as rel, t.rolname as grantee
        from pg_class c
        cross join _casino_test_roles t
        where c.relkind in ('r', 'v', 'm', 'p', 'S', 'f')
          and c.relacl::text like '%' || t.rolname || '=%'
    loop
        execute format('revoke all on %s from %I', g.rel, g.grantee);
    end loop;
end
$$;

-- 3. Memberships, in both directions. A login role is a member of its data role, and the
--    per-test roles are members of shared roles (bed, bed_zoid6). Revoke only the edges that
--    touch a per-test role; the shared role itself is left as it is.
do $$
declare
    e record;
begin
    for e in
        select r.rolname as granted_role, u.rolname as member
        from pg_auth_members m
        join pg_roles r on r.oid = m.roleid
        join pg_roles u on u.oid = m.member
        where r.oid in (select oid from _casino_test_roles)
           or u.oid in (select oid from _casino_test_roles)
    loop
        execute format('revoke %I from %I', e.granted_role, e.member);
    end loop;
end
$$;

-- 4. Drop. Each role is dropped on its own, so one that is still blocked is reported and the
--    others are still removed.
do $$
declare
    t record;
    dropped integer := 0;
    skipped text := '';
begin
    for t in
        select rolname from _casino_test_roles order by rolname
    loop
        begin
            execute format('drop role %I', t.rolname);
            dropped := dropped + 1;
        exception when dependent_objects_still_exist or invalid_grant_operation then
            skipped := skipped || ' ' || t.rolname;
        end;
    end loop;
    raise notice 'drop-casino-test-roles: dropped % role(s).', dropped;
    if skipped <> '' then
        raise warning 'drop-casino-test-roles: still blocked, left in place:%', skipped;
    end if;
end
$$;

select 'per-test roles remaining: ' || count(*) as status
from pg_roles
where rolname ~ '^(m_)?bjconsole' or rolname ~ '^(m_)?bj2p_';

commit;
