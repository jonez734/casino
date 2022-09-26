create table if not exists casino.mapgameplayer (
    "gameid" bigint constraint fk_casino_map_gameid references casino.__game(id) on update cascade on delete cascade,
    "playerid" bigint constraint fk_casino_map_playerid references casino.__player(id) on update cascade on delete cascade
);

grant all on casino.mapgameplayer to apache;
