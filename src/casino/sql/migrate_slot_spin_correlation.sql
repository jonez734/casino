-- casino/sql/migrate_slot_spin_correlation.sql
-- Adds the spin's correlation id, so a retry of the same spin cannot settle twice.
-- Idempotent. Run once per existing database (fresh installs get the column from slots.sql).
--
-- Existing rows keep NULL correlation_id; the unique index is partial, so they do not conflict.

begin;

alter table casino.__slot_spin add column if not exists correlation_id text;

create unique index if not exists uq_slot_spin_correlation
    on casino.__slot_spin(correlation_id) where correlation_id is not null;

commit;
