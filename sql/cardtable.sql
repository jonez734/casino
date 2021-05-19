\echo cardtable
create table casino.__cardtable (
  "id" bigserial unique not null primary key,
  "type" text,
  "minimumbet" numeric(10,0) default 100,
  "maximumbet" numeric(10,0) default 100,
  "location" text,
  "ownerid" bigint constraint fk_cardtable_ownerid references engine.__member(id) on update cascade on delete set null,
  "ownersince" timestamptz,
  "earnings" numeric(10,0),
  "bank" numeric(10,0),
  "cheat" boolean default False,
  "cheatpercent" integer
--  "lastplayed" timestamptz,
--  "lastplayedbyid" integer constraint fk_cardtable_lastplayedbyid references engine.__member(id) on update cascade on delete set null
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

create table map_cardtable_player (
    "cardtableid" bigint constraint fk_cardtable_id references casino.__cardtable(id) on update cascade on delete cascade,
    "playerid" bigint constraint fk_cardtable_playerid references casino.__player(id) on update cascade on delete cascade
);
