create or replace view casino.hand as
    select
        *
    from engine.node where prg = 'casino.hand'
;
