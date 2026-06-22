create table if not exists casino.map_cardtable_player (
    "cardtablemoniker" citext constraint fk_map_cardtable_player_cardtablemoniker references casino.__table(moniker) on update cascade on delete cascade,
    "playermoniker" citext constraint fk_map_cardtable_player_playermoniker references engine.__member(moniker) on update cascade on delete cascade
);

grant select on casino.map_cardtable_player to web;
grant all on casino.map_cardtable_player to term, sysop;
