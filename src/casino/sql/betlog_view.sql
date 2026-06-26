create or replace view casino.betlog as
    select 
        b.*,
        extract(epoch from b.dateposted) as datepostedepoch,
        timezone(currentmember.tz, b.dateposted) as datepostedlocal
    from casino.__betlog as b
    left outer join engine.__member as currentmember on (currentmember.loginid = current_user)
;

grant select on casino.betlog to web, term, sysop;
