create table if not exists casino.__account (
    "id" bigserial unique not null primary key,
    "membermoniker" citext constraint fk_casino_account_membermoniker references engine.__member(moniker) on update cascade on delete set null,
    "amount" numeric(10,2),
    "gameid" bigint,
    "status" text,
    "datestamp" timestamptz,
    "attrs" jsonb
);

grant select on casino.__account to web;
grant all on casino.__account to term, sysop;
grant select on casino.__account_id_seq to web;
grant all on casino.__account_id_seq to term, sysop;
