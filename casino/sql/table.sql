create or replace view casino.table as
    select
      *,
      (attributes->>'minimumbet')::bigint as minimumbet,
      (attributes->>'maximumbet')::bigint as meximumbet,
      (attributes->>'bank')::bigint as bank,
      (attributes->>'casinoid')::bigint as casinoid
    from engine.node where prg='casino.table';
