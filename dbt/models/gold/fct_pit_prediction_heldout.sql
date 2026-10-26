-- The pit-now prediction for every green-flag checked stop, redone with the pit loss estimated without the race it is
-- scored on. fct_pit_now takes the circuit's median loss over every measured stop, including the stops it is then scored
-- on, so its accuracy is in-sample. Here the loss comes from the other races only (leave one session out), by the same
-- rule as fct_circuit_pit_loss: the circuit's median if the other races give at least pit_loss_min_stops stops from at
-- least pit_loss_min_sessions sessions there, otherwise the median over all other races at every circuit.
-- Only green-flag stops are redone: the safety car and VSC losses are the green loss times a ratio that is itself
-- estimated across all races, and redoing that is a larger job than this.
-- The prediction is recomputed here from lap-end times, as in fct_pit_now: 1 + the number of other cars whose lap-end
-- time on the lap before the stop is less than the driver's own plus the loss. predicted_recomputed uses the original
-- loss and must equal the stored in-sample prediction (a test checks this), which shows the recomputation is faithful.
-- loss_recomputed_s is the circuit or global median over ALL races, which must equal the stored in-sample loss too.
with stops as (

    select
        c.pit_stop_key, c.session_key, c.year, c.driver_code, c.in_lap,
        c.pit_loss_s as loss_in_sample_s, c.loss_source as loss_source_in_sample,
        c.predicted_position as predicted_in_sample, c.actual_position, c.other_stops_nearby,
        d.circuit_id
    from {{ ref('fct_pit_prediction_check') }} c
    join {{ ref('dim_session_circuit') }} d on d.session_key = c.session_key
    where c.regime = 'green'

),

sessions as (

    select distinct session_key, circuit_id from stops

),

loss as (

    select session_key, circuit_id, pit_loss_s from {{ ref('fct_pit_loss') }}

),

circuit_other as (

    select s.session_key, count(*) as n, count(distinct l.session_key) as n_sessions, median(l.pit_loss_s) as mid_s
    from sessions s
    join loss l on l.circuit_id = s.circuit_id and l.session_key <> s.session_key
    group by s.session_key

),

global_other as (

    select s.session_key, median(l.pit_loss_s) as mid_s
    from sessions s
    join loss l on l.session_key <> s.session_key
    group by s.session_key

),

circuit_all as (

    select circuit_id, count(*) as n, count(distinct session_key) as n_sessions, median(pit_loss_s) as mid_s
    from loss group by circuit_id

),

global_all as (

    select median(pit_loss_s) as mid_s from loss

),

with_loss as (

    select
        st.*,
        (co.n >= {{ var('pit_loss_min_stops', 10) }} and co.n_sessions >= {{ var('pit_loss_min_sessions', 2) }}) as held_out_circuit,
        case when co.n >= {{ var('pit_loss_min_stops', 10) }} and co.n_sessions >= {{ var('pit_loss_min_sessions', 2) }}
             then co.mid_s else go.mid_s end as loss_held_out_s,
        case when ca.n >= {{ var('pit_loss_min_stops', 10) }} and ca.n_sessions >= {{ var('pit_loss_min_sessions', 2) }}
             then ca.mid_s else ga.mid_s end as loss_recomputed_s
    from stops st
    left join circuit_other co on co.session_key = st.session_key
    left join global_other go on go.session_key = st.session_key
    left join circuit_all ca on ca.circuit_id = st.circuit_id
    cross join global_all ga

),

counted as (

    select
        w.*,
        count(o.driver_code) filter (where o.time_s < me.time_s + w.loss_held_out_s) as ahead_held_out,
        count(o.driver_code) filter (where o.time_s < me.time_s + w.loss_in_sample_s) as ahead_in_sample
    from with_loss w
    join {{ ref('fct_lap_gap') }} me
      on me.session_key = w.session_key and me.driver_code = w.driver_code and me.lap_number = w.in_lap - 1
    left join {{ ref('fct_lap_gap') }} o
      on o.session_key = w.session_key and o.lap_number = w.in_lap - 1 and o.driver_code <> w.driver_code
    group by all

)

select
    pit_stop_key,
    session_key,
    cast(year as integer)                          as year,
    driver_code,
    cast(in_lap as integer)                        as in_lap,
    circuit_id,
    cast(loss_in_sample_s as double)               as loss_in_sample_s,
    cast(loss_recomputed_s as double)              as loss_recomputed_s,
    cast(loss_held_out_s as double)                as loss_held_out_s,
    cast(case when held_out_circuit then 'circuit' else 'global' end as varchar) as loss_source_held_out,
    cast(predicted_in_sample as integer)           as predicted_in_sample,
    cast(1 + ahead_in_sample as integer)           as predicted_recomputed,
    cast(1 + ahead_held_out as integer)            as predicted_held_out,
    cast(actual_position as integer)               as actual_position,
    cast(other_stops_nearby as integer)            as other_stops_nearby
from counted
