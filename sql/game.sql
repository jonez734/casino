\echo game
create table if not exists casino.__cardgame (
    "id" bigserial unique not null primary key,
    "datestarted" timestamptz,
    "minplayer" bigint default 1,
    "maxplayer" bigint default 2,
    "status" text,
    "type" text not null
);

create or replace view casino.cardgame as
    select
      *,
      extract(epoch from datestarted) as datestartedepoch
    from casino.__cardgame
;
