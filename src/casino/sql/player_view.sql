create or replace view casino.player as
    select
        p.*,
        timezone(currentmember.tz, p.lastplayed) as lastplayedlocal
    from casino.__player as p
    left outer join engine.__member as currentmember on (currentmember.loginid = current_user)
;

grant select on casino.player to web, term, sysop;
