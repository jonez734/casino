-- Move ownership of casino objects to the zoid6 owner role.
--
-- casino --install runs DDL as the connecting role. Run as a superuser or a
-- zoid6 member, the tables and views it creates would otherwise stay owned by
-- that login role (for example jam), while the casino schema is zoid6's. Then
-- zoid6-owned code cannot read them, and bed's grants on casino do not reach
-- them. This moves every casino table, view, sequence, and function to zoid6.
--
-- Idempotent: the loop only touches objects whose owner is not already zoid6.
-- Requires the zoid6 role to exist (bbsengine6 checkzoid6role creates it).

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
          and pg_get_userbyid(c.relowner) <> 'zoid6'
    loop
        if r.kind = 'S' then
            execute format('alter sequence casino.%I owner to zoid6', r.name);
        elsif r.kind = 'v' then
            execute format('alter view casino.%I owner to zoid6', r.name);
        elsif r.kind = 'm' then
            execute format('alter materialized view casino.%I owner to zoid6', r.name);
        elsif r.kind = 'f' then
            execute format('alter foreign table casino.%I owner to zoid6', r.name);
        else
            execute format('alter table casino.%I owner to zoid6', r.name);
        end if;
    end loop;

    for r in
        select p.proname as name, pg_get_function_identity_arguments(p.oid) as args
        from pg_proc p
        join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'casino'
          and pg_get_userbyid(p.proowner) <> 'zoid6'
    loop
        execute format('alter function casino.%I(%s) owner to zoid6', r.name, r.args);
    end loop;
end
$owner$;
