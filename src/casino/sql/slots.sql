create table if not exists casino.__slot_spin (
    "id" bigserial unique not null primary key,
    "table_moniker" citext constraint fk_slot_spin_table references casino.__table(moniker) on update cascade on delete cascade,
    "player_moniker" citext constraint fk_slot_spin_player references engine.__member(moniker) on update cascade on delete set null,
    "bet" numeric(10,0) not null check (bet > 0),
    "payout" numeric(10,0) not null check (payout >= 0),
    "reels" jsonb not null,
    "wins" jsonb not null,
    "spun_at" timestamptz not null default now(),
    "correlation_id" text
);

-- One settlement per spin. A retry with the same correlation id finds this row and settles nothing.
-- Partial, so rows from before the column existed (NULL) stay allowed.
create unique index if not exists uq_slot_spin_correlation
    on casino.__slot_spin(correlation_id) where correlation_id is not null;

create index if not exists idx_slot_spin_table_time
    on casino.__slot_spin(table_moniker, spun_at desc);
create index if not exists idx_slot_spin_player_time
    on casino.__slot_spin(player_moniker, spun_at desc);

grant select on casino.__slot_spin to web;
grant all on casino.__slot_spin to term, sysop;
grant select on casino.__slot_spin_id_seq to web;
grant all on casino.__slot_spin_id_seq to term, sysop;
