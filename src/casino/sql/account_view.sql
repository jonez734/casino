create or replace view casino.account as
    select
        a.*,
        extract(epoch from a.datestamp) as datestampepoch,
        timezone(currentmember.tz, a.datestamp) as datestamplocal,
        m.moniker as membername
    from casino.__account as a
    left outer join engine.__member as currentmember on (currentmember.loginid = current_user)
    left join engine.member m on m.moniker = a.membermoniker
;

grant select on casino.account to web, term, sysop;
