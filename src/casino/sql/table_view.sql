create or replace view casino.table as 
    select 
        t.*,
        extract(epoch from t.ownersince) as ownersinceepoch,
        timezone(currentmember.tz, t.ownersince) as ownersincelocal
    from casino.__table as t
    left outer join engine.__member as currentmember on (currentmember.loginid = current_user)
;

grant select on casino.table to web, term, sysop;
