create or replace view casino.log as
    select 
        l.*,
        extract(epoch from l.datestamp) as datestampepoch,
        timezone(currentmember.tz, l.datestamp) as datestamplocal
    from casino.__log as l
    left outer join engine.__member as currentmember on (currentmember.loginid = current_user)
;

grant select on casino.log to web, term, sysop;
