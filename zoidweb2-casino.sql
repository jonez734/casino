create schema "casino";

grant all on schema casino to apache;

create table casino.__cardtable (
  "id" serial unique not null primary key,
  "type" text,
  "minimumbet" numeric(10,0) default 100,
  "maximumbet" numeric(10,0) default 100,
  "location" text,
  "ownerid" integer constraint fk_cardtable_ownerid references engine.__member(id) on update cascade on delete set null,
  "ownersince" timestamptz,
  "earnings" numeric(10,0),
  "bank" numeric(10,0),
  "cheat" boolean default False,
  "cheatpercent" integer,
  "lastplayed" timestamptz,
  "lastplayedbyid" integer constraint fk_cardtable_lastplayedbyid references engine.__member(id) on update cascade on delete set null
);

grant all on casino.__cardtable to apache;
grant all on casino.__cardtable_id_seq to apache;

create view casino.cardtable as 
  select __cardtable.*,
  extract(epoch from lastplayed) as lastplayedepoch,
  extract(epoch from ownersince) as ownersinceepoch,
  m1.name as ownermembername,
  m2.name as lastplayedbyname
  from casino.__cardtable
  left join engine.member m1 on m1.id = casino.__cardtable.ownerid
  left join engine.member m2 on m2.id = casino.__cardtable.lastplayedbyid
;

grant all on casino.cardtable to apache;

create table casino.__betlog (
    "id" serial unique not null primary key,
    "memberid" integer constraint fk_betlog_memberid references engine.__member(id) on update cascade on delete set null,
    "cardtableid" integer constraint fk_betlog_cardtableid references casino.__cardtable(id) on update cascade on delete set null,
    "amount" numeric(10,0) not null,
    "dateposted" timestamptz,
    "description" text
);

grant all on casino.__betlog to apache;

create view casino.betlog as
    select __betlog.*,
    extract(epoch from dateposted) as datepostedepoch,
    m1.name as membername
  from casino.__betlog
  LEFT JOIN engine.member m1 ON m1.id = casino.__betlog.memberid
;

grant all on casino.__betlog_id_seq to apache;
grant all on casino.betlog to apache;

create table casino.__player (
  "id" serial unique not null primary key,
  "memberid" integer constraint fk_player_memberid references engine.__member(id) on update cascade on delete set null,
  "location" text,
  "lastplayed" timestamptz,
  "credits" numeric(10,2)
);

grant all on casino.__player_id_seq to apache;
grant all on casino.__player to apache;

create view casino.player as
  select casino.__player.*,
    m1.name as membername
  from casino.__player
  left join engine.member m1 on m1.id = casino.__player.memberid
;

grant all on casino.player to apache;
