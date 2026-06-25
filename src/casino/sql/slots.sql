create table if not exists casino.__slot_spin (
    "id" bigserial unique not null primary key,
    "table_moniker" citext constraint fk_slot_spin_table references casino.__table(moniker) on update cascade on delete cascade,
    "player_moniker" citext constraint fk_slot_spin_player references engine.__member(moniker) on update cascade on delete set null,
    "bet" numeric(10,0) not null check (bet > 0),
    "payout" numeric(10,0) not null check (payout >= 0),
    "reels" jsonb not null,
    "wins" jsonb not null,
    "spun_at" timestamptz not null default now()
);

create index if not exists idx_slot_spin_table_time
    on casino.__slot_spin(table_moniker, spun_at desc);
create index if not exists idx_slot_spin_player_time
    on casino.__slot_spin(player_moniker, spun_at desc);

grant select on casino.__slot_spin to web;
grant all on casino.__slot_spin to term, sysop;
grant select on casino.__slot_spin_id_seq to web;
grant all on casino.__slot_spin_id_seq to term, sysop;
