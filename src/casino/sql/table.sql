create table if not exists casino.__table (
    "moniker" citext unique not null primary key,
    "type" text,
    "minimumbet" numeric(10,0) default 100,
    "maximumbet" numeric(10,0) default 100,
    "location" text,
    "ownermoniker" citext constraint fk_table_ownermoniker references engine.__member(moniker) on update cascade on delete set null,
    "ownersince" timestamptz,
    "accountid" bigint constraint fk_table_accountid references bank.__account(id) on delete set null,
    "earnings" numeric(10,0),
    "cheat" boolean default False,
    "cheatpercent" integer,
    "attrs" jsonb,
    "shoe_cards" text[] default null,
    "shoe_uses" integer default 0,
    "status" text default 'open',
    "dealermodule" text,
    "playermodule" text
);

grant select on casino.__table to web;
grant all on casino.__table to term, sysop;
