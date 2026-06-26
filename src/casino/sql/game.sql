create table if not exists casino.__game (
    "id" bigserial unique not null primary key,
    "tablemoniker" citext references casino.__table(moniker) on update cascade on delete cascade,
    "handid" bigint,
    "playermoniker" citext references engine.__member(moniker) on update cascade on delete set null,
    "kind" text not null,
    "status" text,
    "datestarted" timestamptz,
    "dateended" timestamptz,
    "attrs" jsonb,
    "logicmodulepath" text,
    "dealermodulepath" text
);

grant select on casino.__game to web;
grant all on casino.__game to term, sysop;
grant select on casino.__game_id_seq to web;
grant all on casino.__game_id_seq to term, sysop;
