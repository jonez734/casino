create table if not exists casino.__betlog (
    "id" bigserial unique not null primary key,
    "memberid" bigint constraint fk_betlog_memberid references engine.__member(id) on update cascade on delete set null,
    "cardtableid" bigint constraint fk_betlog_cardtableid references casino.__cardtable(id) on update cascade on delete set null,
    "cardgameid" bigint constraint fk_betlog_gameid references casino.__cardgame(id) on update cascade on delete cascade,
    "playerid" bigint constraint fk_betlog_playerid references casino.__player(id) on update cascade on delete cascade,
    "amount" numeric(10,0) not null,
    "status" text,
    "dateposted" timestamptz,
    "description" text
);

grant all on casino.__betlog to apache;

create or replace view casino.betlog as
 select __betlog.*,
  extract(epoch from dateposted) as datepostedepoch,
  m1.name as membername
 from casino.__betlog
 LEFT JOIN engine.member m1 ON m1.id = casino.__betlog.memberid
;

grant all on casino.__betlog_id_seq to apache;
grant all on casino.betlog to apache;
