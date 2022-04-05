\echo game
--create table if not exists casino.__game (
--    "id" bigserial unique not null primary key,
--    "datestarted" timestamptz,
--    "minplayer" bigint default 1,
--    "maxplayer" bigint default 2,
--    "status" text,
--    "type" text not null
--);

--create or replace view casino.game as
--    select
--      g.*,
--      extract(epoch from g.datestarted) as datestartedepoch
--    from casino.__game as g
--;

create or replace view casino.game as
  select
    *,
    (attributes->>'casinoid')::bigint as casinoid,
    (attributes->>'handid')::bigint as handid
    (attributes->>'playerid')::bigint as playerid
  from engine.node
  where prg='casino.game'
;
