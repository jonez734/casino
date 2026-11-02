-- Move ownership of casino's objects to the casino_obj owner role.
--
-- Covers tables, views, sequences, and functions in the casino schema. The casino
-- schema itself stays owned by zoid6: public.manage_schema_priv (zoid6-owned) issues
-- casino's schema grants, and a NOLOGIN casino_obj cannot grant on a schema it does
-- not own. Objects are owned by casino_obj, which is what the object manifest checks.
--
-- Idempotent: the loop only touches objects whose owner is not already casino_obj.
-- Requires the casino_obj role to exist (casino.startup.checkcasino creates it).

do $owner$
declare
    r record;
begin
    for r in
        select c.relname as name, c.relkind as kind
        from pg_class c
        join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'casino'
          and c.relkind in ('r', 'v', 'S', 'm', 'p', 'f')
          and pg_get_userbyid(c.relowner) <> 'casino_obj'
    loop
        if r.kind = 'S' then
            execute format('alter sequence casino.%I owner to casino_obj', r.name);
        elsif r.kind = 'v' then
            execute format('alter view casino.%I owner to casino_obj', r.name);
        elsif r.kind = 'm' then
            execute format('alter materialized view casino.%I owner to casino_obj', r.name);
        elsif r.kind = 'f' then
            execute format('alter foreign table casino.%I owner to casino_obj', r.name);
        else
            execute format('alter table casino.%I owner to casino_obj', r.name);
        end if;
    end loop;

    for r in
        select p.proname as name, pg_get_function_identity_arguments(p.oid) as args
        from pg_proc p
        join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'casino'
          and pg_get_userbyid(p.proowner) <> 'casino_obj'
    loop
        execute format('alter function casino.%I(%s) owner to casino_obj', r.name, r.args);
    end loop;
end
$owner$;
