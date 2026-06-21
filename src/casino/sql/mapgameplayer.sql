create table if not exists casino.mapgameplayer (
    "gameid" bigint constraint fk_casino_map_gameid references casino.__game(id) on update cascade on delete cascade,
    "playermoniker" citext constraint fk_casino_map_playermoniker references engine.__member(moniker) on update cascade on delete cascade
);

grant select on casino.mapgameplayer to web;
grant all on casino.mapgameplayer to term, sysop;
