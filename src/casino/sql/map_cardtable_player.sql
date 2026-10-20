create table if not exists casino.map_cardtable_player (
    "cardtablemoniker" citext not null constraint fk_map_cardtable_player_cardtablemoniker references casino.__table(moniker) on update cascade on delete cascade,
    "playermoniker" citext constraint fk_map_cardtable_player_playermoniker references engine.__member(moniker) on update cascade on delete cascade,
    -- 'player': holds a seat. 'spectator': watching, not seated.
    -- 'dealer': a real member holding the table's dealer seat. Virtual
    -- (bot) dealers have no row here.
    "role" text not null default 'player'
        constraint ck_map_cardtable_player_role check (role in ('player', 'spectator', 'dealer')),
    "joinedat" timestamptz default now()
);

-- A member appears at a table once, in one role.
create unique index if not exists uq_map_cardtable_player_member
    on casino.map_cardtable_player (cardtablemoniker, playermoniker)
    where playermoniker is not null;

-- At most one dealer per table.
create unique index if not exists uq_map_cardtable_player_dealer
    on casino.map_cardtable_player (cardtablemoniker)
    where role = 'dealer';

create index if not exists idx_map_cardtable_player_moniker
    on casino.map_cardtable_player (playermoniker);

grant select on casino.map_cardtable_player to web;
grant all on casino.map_cardtable_player to term, sysop;
