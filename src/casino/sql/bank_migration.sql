-- casino/sql/bank_migration.sql
-- Bank transaction tracking tables

-- Table to track individual bank transactions
create table if not exists casino.__banktransaction (
    "id" serial unique not null primary key,
    "tablemoniker" citext constraint fk_banktransaction_table references casino.__table(moniker) on update cascade on delete cascade,
    "amount" numeric(10,0) not null,
    "transactiontype" text not null, -- 'buyin', 'payout', 'win', 'loss', 'adjustment', 'transfer_in', 'transfer_out'
    "source" text, -- 'table' (table bank), 'player' (player account), 'house' (system), 'transfer'
    "destination" text, -- 'table', 'player', 'house'
    "relatedmoniker" citext, -- for transfers, the other table; for player transactions, the player moniker
    "description" text,
    "membermoniker" citext, -- who initiated this transaction
    "dateposted" timestamptz default now()
);

create index idx_banktransaction_table on casino.__banktransaction(tablemoniker);
create index idx_banktransaction_date on casino.__banktransaction(dateposted);

grant select on casino.__banktransaction to web;
grant all on casino.__banktransaction to term, sysop;
grant all on casino.__banktransaction_id_seq to term, sysop;

-- View for bank transactions
create or replace view casino.banktransaction as
  select __banktransaction.*,
         extract(epoch from dateposted) as datepostedepoch,
         timezone(currentmember.tz, dateposted) as datepostedlocal
  from casino.__banktransaction
  left outer join engine.__member currentmember on (currentmember.loginid = current_user);

grant select on casino.banktransaction to web, term, sysop;

-- Pending transfer requests (require approval)
create table if not exists casino.__tabletransfer (
    "id" serial unique not null primary key,
    "fromtable" citext constraint fk_tabletransfer_from references casino.__table(moniker) on update cascade on delete cascade,
    "totable" citext constraint fk_tabletransfer_to references casino.__table(moniker) on update cascade on delete cascade,
    "amount" numeric(10,0) not null,
    "status" text default 'pending', -- 'pending', 'approved', 'rejected', 'cancelled'
    "requestedby" citext, -- moniker who requested the transfer
    "requestedat" timestamptz default now(),
    "respondedby" citext, -- moniker who approved/rejected
    "respondedat" timestamptz
);

create index idx_tabletransfer_status on casino.__tabletransfer(status);
create index idx_tabletransfer_tables on casino.__tabletransfer(fromtable, totable);

grant select on casino.__tabletransfer to web;
grant all on casino.__tabletransfer to term, sysop;
grant all on casino.__tabletransfer_id_seq to term, sysop;

-- View for table transfers
create or replace view casino.tabletransfer as
  select __tabletransfer.*,
         extract(epoch from requestedat) as requestedatepoch,
         timezone(currentmember.tz, requestedat) as requestedatlocal,
         extract(epoch from respondedat) as respondedatepoch,
         timezone(currentmember.tz, respondedat) as respondedatlocal
  from casino.__tabletransfer
  left outer join engine.__member currentmember on (currentmember.loginid = current_user);

grant select on casino.tabletransfer to web, term, sysop;

-- Table settings for bank limits
alter table casino.__table add column if not exists "maxtransfer" numeric(10,0) default 1000;
