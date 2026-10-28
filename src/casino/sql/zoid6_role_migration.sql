-- casino/sql/zoid6_role_migration.sql
-- Migration: the daemon's database login, bed_zoid6. Idempotent.
--
-- bed_zoid6 is the login the zoid6 daemon connects as. The daemon runs as the OS user zoid6, and
-- an identd map (pg_ident.conf: zoidmap zoid6 bed_zoid6) makes that user log in as bed_zoid6, so
-- the login needs no password. The role is LOGIN and NOINHERIT: it holds nothing except through
-- its own grants.
--
-- Every privilege bed holds on the engine and casino schemas is copied to bed_zoid6, read from the
-- catalog ACLs, so nothing is hand-listed. bed itself is not changed here: it stays as the rollback
-- login until verification passes. zoid6_role_cutover.sql removes it.
--
-- The owner zoid6 is not a login and is not changed.
--
-- Run this as the schema owner (zoid6) or a zoid6 member. Functions owned by zoid6 can only be
-- granted by their owner: run as another role, the EXECUTE copies for those functions produce a
-- WARNING and grant nothing. The migration reports them so the gap is visible, not silent.

do $bed_zoid6$
begin
    if not exists (select 1 from pg_roles where rolname = 'bed_zoid6') then
        create role bed_zoid6 login noinherit nosuperuser nocreatedb nocreaterole;
    end if;
end
$bed_zoid6$;

-- Copy schema USAGE (and CREATE, if bed holds it) from bed's schema ACL.
do $schemas$
declare
    s record;
    privs text;
begin
    for s in
        select n.nspname as nsp, a.privilege_type as priv
          from pg_namespace n,
               aclexplode(n.nspacl) a
         where n.nspname in ('engine', 'casino')
           and a.grantee = (select oid from pg_roles where rolname = 'bed')
    loop
        if s.priv = 'USAGE' then
            execute format('grant usage on schema %I to bed_zoid6', s.nsp);
        elsif s.priv = 'CREATE' then
            execute format('grant create on schema %I to bed_zoid6', s.nsp);
        end if;
    end loop;
end
$schemas$;

-- Copy table, view, and sequence privileges from bed's relation ACLs.
do $relations$
declare
    r record;
    cmd text;
begin
    for r in
        select n.nspname as nsp, c.relname as name, c.relkind as kind,
               array_agg(a.privilege_type::text order by a.privilege_type) as privs
          from pg_class c
          join pg_namespace n on n.oid = c.relnamespace,
               aclexplode(c.relacl) a
         where n.nspname in ('engine', 'casino')
           and c.relkind in ('r', 'v', 'S', 'm', 'p', 'f')
           and a.grantee = (select oid from pg_roles where rolname = 'bed')
         group by n.nspname, c.relname, c.relkind
    loop
        if r.kind = 'S' then
            -- Sequences take USAGE and SELECT, as the catalog records them.
            cmd := format('grant %s on sequence %I.%I to bed_zoid6',
                          array_to_string(r.privs, ', '), r.nsp, r.name);
        else
            cmd := format('grant %s on %I.%I to bed_zoid6',
                          array_to_string(r.privs, ', '), r.nsp, r.name);
        end if;
        execute cmd;
    end loop;
end
$relations$;

-- Copy EXECUTE on functions bed may call (the engine and casino function surface).
do $functions$
declare
    f record;
begin
    for f in
        select p.oid::regprocedure::text as sig
          from pg_proc p
          join pg_namespace n on n.oid = p.pronamespace,
               aclexplode(p.proacl) a
         where n.nspname in ('engine', 'casino')
           and a.grantee = (select oid from pg_roles where rolname = 'bed')
           and a.privilege_type = 'EXECUTE'
    loop
        execute format('grant execute on function %s to bed_zoid6', f.sig);
    end loop;
end
$functions$;

-- The daemon's login is a principal, so it has a member row (the foreign key from engine.pgrole
-- requires one). It has no password: identd authenticates the connection. It is approved so it
-- is not treated as a pending signup, and its email is a placeholder, since a daemon has no mailbox.
insert into engine.__member (moniker, email, approved, loginid)
values ('bed_zoid6', 'bed_zoid6@localhost', true, 'bed_zoid6')
on conflict (moniker) do nothing;

-- Track the daemon's login the same way members are tracked (jam -> jam pattern).
insert into engine.pgrole (membermoniker, rolname, created_at)
values ('bed_zoid6', 'bed_zoid6', now())
on conflict (membermoniker) do nothing;
