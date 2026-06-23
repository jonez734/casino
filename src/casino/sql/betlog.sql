create table if not exists casino.__betlog (
    "id" bigserial unique not null primary key,
    "membermoniker" citext constraint fk_betlog_membermoniker references engine.__member(moniker) on update cascade on delete set null,
    "cardtablemoniker" citext constraint fk_betlog_cardtablemoniker references casino.__table(moniker) on update cascade on delete set null,
    "gameid" bigint constraint fk_betlog_gameid references casino.__game(id) on update cascade on delete cascade,
    "playermoniker" citext constraint fk_betlog_playermoniker references engine.__member(moniker) on update cascade on delete set null,
    "hand_id" bigint constraint fk_betlog_hand_id references casino.__hand(id) on update cascade on delete set null,
    "amount" numeric(10,0) not null,
    "status" text,
    "dateposted" timestamptz,
    "notes" text,
    "currenthand" text,
    "description" text,
    "attrs" jsonb
);

create index if not exists idx_betlog_hand_id on casino.__betlog(hand_id) where hand_id is not null;

-- Migration: add notes, currenthand, and hand_id if they don't exist (for existing databases)
do $$
begin
    if not exists (select 1 from information_schema.columns where table_name = '__betlog' and column_name = 'notes') then
        alter table casino.__betlog add column notes text;
    end if;
    if not exists (select 1 from information_schema.columns where table_name = '__betlog' and column_name = 'currenthand') then
        alter table casino.__betlog add column currenthand text;
    end if;
    if not exists (select 1 from information_schema.columns where table_name = '__betlog' and column_name = 'hand_id') then
        alter table casino.__betlog add column hand_id bigint references casino.__hand(id) on update cascade on delete set null;
    end if;
end $$;

grant select on casino.__betlog to web;
grant all on casino.__betlog to term, sysop;
grant select on casino.__betlog_id_seq to web;
grant all on casino.__betlog_id_seq to term, sysop;
