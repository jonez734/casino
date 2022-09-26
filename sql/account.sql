--create table casino.__account (
--    "id" bigserial unique not null primary key,
--    "memberid" bigint constraint fk_casino_account_memberid references engine.__member(id) on update cascade on delete set null,
--    "amount" numeric(10,2),
--    "gameid" bigint constraint fk_casino_account_gameid references casino.__game(id) on update cascade on delete set null,
--    "status" text,
--    "datestamp" timestamptz
--);

--create or replace view casino.account as
--    select a.*,
--    extract(epoch from datestamp) as datestampepoch
--    from casino.__account as a
--;

create or replace view casino.account as
    select
      *,
      (attributes->>'amount')::bigint as amount,
      (attributes->>'gameid')::bigint as gameid,
      (attributes->>'status')::text as status
    from engine.node
    where prg='casino.account'
;
grant select on casino.account to apache;
--grant all on casino.__account to apache;
