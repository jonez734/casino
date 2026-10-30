-- create-casino-test-role.sql
--
-- Creates the casino_test role: the privileges the casino test suites need on casino and engine
-- objects, granted to one non-login role. Per-test login roles become members of it, so they
-- inherit the grants. Production grants (src/casino/sql/*.sql) are not changed.
--
-- Idempotent: safe to run more than once. The second run changes nothing.
--
-- Run as jam (superuser) against the test database only:
--
--   psql -U jam -d zoid6test -v ON_ERROR_STOP=1 -f scripts/create-casino-test-role.sql
--
-- The script refuses to run against any other database.

\set ON_ERROR_STOP on

-- Guard: only the test database.
do $$
begin
    if current_database() <> 'zoid6test' then
        raise exception 'create-casino-test-role: refusing to run against %, only zoid6test',
            current_database();
    end if;
end
$$;

-- The role. NOLOGIN: it is granted to login roles, it never connects itself.
do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'casino_test') then
        create role casino_test nologin;
    end if;
end
$$;

-- Schemas: the role must be able to see the objects below.
grant usage on schema casino, engine to casino_test;

-- Tables and views: the same privileges opencode and m_opencode hold on casino and engine.
-- grant ... on all ... is itself idempotent, so repeating it is harmless.
grant select, insert, update, delete on all tables in schema casino to casino_test;
grant select, insert, update, delete on all tables in schema engine to casino_test;
grant usage, select on all sequences in schema casino to casino_test;
grant usage, select on all sequences in schema engine to casino_test;

-- Views (casino.player and friends) are relations too, but "all tables" does not include them.
do $$
declare
    r record;
begin
    for r in
        select n.nspname, c.relname
        from pg_class c
        join pg_namespace n on n.oid = c.relnamespace
        where n.nspname in ('casino', 'engine')
          and c.relkind = 'v'
    loop
        execute format('grant select, insert, update, delete on %I.%I to casino_test',
                       r.nspname, r.relname);
    end loop;
end
$$;

-- The fixture runs as opencode and attaches per-test roles to casino_test, so opencode needs
-- admin option on it. Granting it again changes nothing.
do $$
begin
    if not exists (
        select 1
        from pg_auth_members m
        join pg_roles r on r.oid = m.roleid
        join pg_roles u on u.oid = m.member
        where r.rolname = 'casino_test'
          and u.rolname = 'opencode'
          and m.admin_option
    ) then
        grant casino_test to opencode with admin option;
    end if;
end
$$;

-- Verify the grants took effect. Postgres only warns, and ON_ERROR_STOP does not stop on a
-- warning, so a grant issued by a role that does not own the objects silently grants nothing.
-- Check the privileges directly and fail if any are missing.
do $$
declare
    missing text := '';
begin
    if not has_schema_privilege('casino_test', 'casino', 'usage') then
        missing := missing || ' schema casino';
    end if;
    if not has_schema_privilege('casino_test', 'engine', 'usage') then
        missing := missing || ' schema engine';
    end if;
    if not has_table_privilege('casino_test', 'casino.player', 'select') then
        missing := missing || ' casino.player';
    end if;
    if not has_table_privilege('casino_test', 'engine.__member', 'select') then
        missing := missing || ' engine.__member';
    end if;
    if missing <> '' then
        raise exception 'create-casino-test-role: grants did not take effect on:%. '
            'Run this script as the owner of these objects (zoid6), or as jam.', missing;
    end if;
end
$$;

select 'casino_test ready on ' || current_database() as status;
