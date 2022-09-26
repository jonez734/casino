create or replace view casino.log as
    select
        *,
        (attributes->>'casinoid')::bigint as casinoid,
        (attributes->>'cardtableid')::bigint as cardtableid,
        (attributes->>'gameid')::bigint as gameid,
        (attributes->>'memberid')::bigint as memberid,
        (attributes->>'playerid')::bigint as playerid,
        (attributes->>'message')::text as message
    where prg='casino.log'
;
        
--create table if not exists casino.__log (
--    "id" bigserial,
--    "memberid" bigint constraint fk_casino_log_memberid references engine.__member(id) on update cascade on delete cascade,
--    "cardtableid" bigint constraint fk_casino_log_cardtableid references casino.__cardtable(id) on update cascade on delete cascade,
--    "gameid" bigint constraint fk_casino_log_gameid references casino.__game(id) on update cascade on delete cascade,
--    "accountid" bigint constraint fk_casino_log_accountid references casino.__account(id) on update cascade on delete set cascade,
--    "datestamp" timestamptz,
--    "message" text
--);

--grant all on casino.__log to apache;

--create or replace view casino.log as
--    select 
--        *,
--        extract(epoch from datestamp) as datestampepoch
--    from casino.__log
--;
