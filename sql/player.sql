create table if not exists casino.__player (
  "id" bigserial unique not null primary key,
  "memberid" integer constraint fk_player_memberid references engine.__member(id) on update cascade on delete set null,
  "location" text,
  "lastplayed" timestamptz
);

--grant all on casino.__player_id_seq to apache;
--grant all on casino.__player to apache;

create or replace view casino.player as
  select 
    casino.__player.*,
    m1.name as membername
  from casino.__player
  left join engine.member m1 on m1.id = casino.__player.memberid
;

grant all on casino.player to apache;
