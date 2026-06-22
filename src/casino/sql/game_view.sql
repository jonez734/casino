create or replace view casino.game as
    select
        g.*,
        extract(epoch from g.datestarted) as datestartedepoch,
        timezone(currentmember.tz, g.datestarted) as datestartedlocal,
        timezone(currentmember.tz, g.dateended) as dateendedlocal,
        m.moniker as playermembername,
        p.players
    from casino.__game as g
    left outer join engine.__member as currentmember on (currentmember.loginid = current_user)
    left join engine.member m on m.moniker = g.playermoniker
    left join (
        select gameid, array_agg(playermoniker) as players
        from casino.map_game_player
        group by gameid
    ) as p on p.gameid = g.id
;

grant select on casino.game to web, term, sysop;
