-- Green-flag pit loss per circuit: the median over every measured stop there, layouts merged.
--
-- In a held-out test (each session predicted from the other sessions, 4,042 stops, 2018-2026) the circuit
-- median had a mean error of 2.67 s against 3.24 s for one global figure; splitting by layout did not help.
-- A circuit seen in only one race, or with few stops, is mostly that one race's conditions, so use the
-- global median where is_reliable is false. is_reliable needs at least pit_loss_min_stops stops from at
-- least pit_loss_min_sessions sessions (defaults 10 and 2, a judgement call, override with --vars).
select
    circuit_id,
    any_value(circuit_name)                                                      as circuit_name,
    count(*)                                                                     as stops,
    count(distinct session_key)                                                  as sessions,
    count(distinct year)                                                         as seasons,
    median(pit_loss_s)                                                           as median_pit_loss_s,
    quantile_cont(pit_loss_s, 0.25)                                              as p25_pit_loss_s,
    quantile_cont(pit_loss_s, 0.75)                                              as p75_pit_loss_s,
    (count(*) >= {{ var('pit_loss_min_stops', 10) }}
     and count(distinct session_key) >= {{ var('pit_loss_min_sessions', 2) }})   as is_reliable
from {{ ref('fct_pit_loss') }}
group by circuit_id
