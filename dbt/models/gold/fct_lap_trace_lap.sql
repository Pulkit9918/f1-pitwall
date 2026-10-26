-- One row per race, sprint or qualifying lap from the year in trace_from_year, saying whether the lap has a usable distance trace
-- and, if not, why (trace_reason, first match wins):
--   standing_start    lap 1: it starts from the grid slot, not the line, so its distances do not line up with other laps
--   pit_lap           the lap has a pit entry or exit: the pit lane is not the racing line
--   no_telemetry      no position samples in the lap
--   late_start / early_end / data_gap   position updates miss the start or end of the lap, go silent mid-lap, or
--                     come too slowly (a session that repeats each position for several samples, then jumps)
--   layout_unreliable the layout has no reliable reference length (dim_layout_length)
--   length_off        the x/y path is more than 4% from the layout's reference length
-- speed_ok says whether the lap's speed channel can be trusted: the speed integral must be within 5% of the x/y
-- distance. A lap with a trace but speed_ok false keeps its time-against-distance trace; speed, throttle, gear, DRS
-- and brake are left empty for it in fct_lap_trace.
with laps as (

    select
        l.lap_key, l.session_key, l.year, l.round, l.session_code, l.driver_code, l.lap_number, l.lap_time_s,
        (l.pit_in_time_s is not null or l.pit_out_time_s is not null) as is_pit_lap,
        d.circuit_layout_key
    from {{ ref('fct_lap') }} as l
    join {{ ref('dim_session_circuit') }} as d on d.session_key = l.session_key
    where l.session_code in ('R', 'S', 'Q', 'SQ', 'SS')
      and l.year >= {{ var('trace_from_year', 2024) }}
      and l.lap_start_time_s is not null
      and l.time_s is not null
      and l.time_s > l.lap_start_time_s

),

joined as (

    select
        laps.*,
        t.n_samples, t.lap_elapsed_s, t.first_gap_s, t.last_gap_s, t.max_gap_s, t.integrated_m, t.car_integrated_m,
        r.ref_length_m, coalesce(r.is_reliable, false) as layout_reliable
    from laps
    left join {{ ref('fct_lap_sample_total') }} as t on t.lap_key = laps.lap_key
    left join {{ ref('dim_layout_length') }} as r on r.circuit_layout_key = laps.circuit_layout_key

),

judged as (

    select
        *,
        integrated_m / ref_length_m       as length_ratio,
        car_integrated_m / integrated_m   as speed_ratio,
        case
            when lap_number = 1 then 'standing_start'
            when is_pit_lap then 'pit_lap'
            when n_samples is null then 'no_telemetry'
            when first_gap_s > {{ var('trace_max_edge_gap_s', 0.8) }} then 'late_start'
            when last_gap_s > {{ var('trace_max_edge_gap_s', 0.8) }} then 'early_end'
            when max_gap_s > {{ var('trace_max_gap_s', 1.5) }} then 'data_gap'
            when not layout_reliable then 'layout_unreliable'
            when abs(integrated_m / ref_length_m - 1) > 0.04 then 'length_off'
            else 'ok'
        end as trace_reason
    from joined

)

select
    lap_key,
    session_key,
    year,
    round,
    session_code,
    driver_code,
    cast(lap_number as integer)        as lap_number,
    circuit_layout_key,
    lap_time_s,
    cast(n_samples as integer)         as n_samples,
    lap_elapsed_s,
    first_gap_s,
    last_gap_s,
    max_gap_s,
    integrated_m,
    ref_length_m,
    length_ratio,
    speed_ratio,
    trace_reason = 'ok'                                                      as has_trace,
    trace_reason = 'ok' and coalesce(abs(speed_ratio - 1) <= 0.05, false)    as speed_ok,
    trace_reason
from judged
