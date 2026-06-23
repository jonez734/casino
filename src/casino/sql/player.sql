create table if not exists casino.__player (
    "id" bigserial unique not null primary key,
    "membermoniker" citext constraint fk_player_membermoniker references engine.__member(moniker) on update cascade on delete set null,
    "location" text,
    "lastplayed" timestamptz,
    "attrs" jsonb,
    "stats" jsonb default '{}'::jsonb
);

grant select on casino.__player to web, term, sysop;
grant all on casino.__player to term, sysop;
grant select on casino.__player_id_seq to web;
grant all on casino.__player_id_seq to term, sysop;
