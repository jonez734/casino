create or replace view casino.slot_spin as
    select
        s.*
    from casino.__slot_spin as s
    left outer join engine.__member as currentmember
        on (currentmember.loginid = current_user)
;

grant select on casino.slot_spin to web, term, sysop;
