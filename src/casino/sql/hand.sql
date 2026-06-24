create table if not exists casino.__hand (
    "id" bigserial unique not null primary key,
    "gameid" bigint references casino.__game(id) on update cascade on delete cascade,
    "playermoniker" citext references engine.__member(moniker) on update cascade on delete set null,
    "cards" jsonb,
    "attrs" jsonb
);

grant select on casino.__hand to web;
grant all on casino.__hand to term, sysop;
grant select on casino.__hand_id_seq to web;
grant all on casino.__hand_id_seq to term, sysop;
