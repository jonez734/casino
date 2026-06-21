create table if not exists casino.__log (
    "id" bigserial,
    "membermoniker" citext constraint fk_casino_log_membermoniker references engine.__member(moniker) on update cascade on delete cascade,
    "cardtableid" bigint constraint fk_casino_log_cardtableid references casino.__table(id) on update cascade on delete cascade,
    "gameid" bigint constraint fk_casino_log_gameid references casino.__game(id) on update cascade on delete cascade,
    "accountid" bigint constraint fk_casino_log_accountid references casino.__account(id) on update cascade on delete cascade,
    "datestamp" timestamptz,
    "message" text,
    "attrs" jsonb
);

grant select on casino.__log to web;
grant all on casino.__log to term, sysop;
grant select on casino.__log_id_seq to web;
grant all on casino.__log_id_seq to term, sysop;
