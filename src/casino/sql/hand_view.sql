create or replace view casino.hand as
    select 
        h.*,
        timezone(currentmember.tz, current_timestamp) as dummylocal
    from casino.__hand as h
    left outer join engine.__member as currentmember on (currentmember.loginid = current_user)
;

grant select on casino.hand to web, term, sysop;
