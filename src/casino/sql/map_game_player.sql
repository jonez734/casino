create table if not exists casino.map_game_player (
    "gameid" bigint constraint fk_casino_map_gameid references casino.__game(id) on update cascade on delete cascade,
    "playermoniker" citext constraint fk_casino_map_playermoniker references engine.__member(moniker) on update cascade on delete cascade
);

grant select on casino.map_game_player to web;
grant all on casino.map_game_player to term, sysop;

