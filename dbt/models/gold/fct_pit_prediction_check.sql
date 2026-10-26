-- One row per real pit stop in a race or sprint, with what fct_pit_now predicted for it and what happened.
-- The prediction is the one made on the lap before the stop (a stop in lap L is the "pit at the end of lap L-1" that
-- fct_pit_now describes), so it uses only what was known then. The outcome is the driver's position at the end of the
-- out-lap (lap L+1): by then the car is back on track and the field has had a lap to settle.
-- Stops are left out when there is nothing to compare: no prediction (red flag, no gap data for lap L-1), or no
-- position at the end of the out-lap (the driver retired, or was lapped out of the data).
-- error is predicted minus actual: positive means the model expected a worse place than the driver got. in_range says
-- whether the actual place is inside the model's own range (predicted_position_fast to predicted_position_slow).
-- other_stops_nearby counts other drivers' stops in laps L-1 to L+1 (the lap the prediction was made on, which a car in
-- the pit lane distorts, the stop lap and the out-lap): the model assumes every other car stays out and holds its pace,
-- so a stop with other_stops_nearby = 0 is the fair test of the loss figure alone.
with stops as (

    select pit_stop_key, session_key, driver_code, in_lap, compound_before, compound_after
    from {{ ref('fct_pit_stop') }}
    where is_race_session
      and in_lap >= 2

),

nearby as (

    select s.pit_stop_key, count(o.pit_stop_key) as other_stops_nearby
    from stops s
    left join stops o
      on o.session_key = s.session_key
     and o.driver_code <> s.driver_code
     and o.in_lap between s.in_lap - 1 and s.in_lap + 1
    group by s.pit_stop_key

),

joined as (

    select
        s.pit_stop_key, s.session_key, s.driver_code, s.in_lap,
        p.year, p.round, p.session_code, p.regime, p.loss_source, p.pit_loss_s, p.position_now,
        p.predicted_position, p.predicted_position_fast, p.predicted_position_slow, p.predicted_position_global, p.margin_s,
        a.position as actual_position,
        n.other_stops_nearby
    from stops s
    join {{ ref('fct_pit_now') }} p
      on p.session_key = s.session_key and p.driver_code = s.driver_code and p.lap_number = s.in_lap - 1
    join {{ ref('fct_lap_gap') }} a
      on a.session_key = s.session_key and a.driver_code = s.driver_code and a.lap_number = s.in_lap + 1
    join nearby n on n.pit_stop_key = s.pit_stop_key
    where p.predicted_position is not null
      and a.position is not null

)

select
    pit_stop_key,
    session_key,
    cast(year as integer)                          as year,
    cast(round as integer)                         as round,
    cast(session_code as varchar)                  as session_code,
    driver_code,
    cast(in_lap as integer)                        as in_lap,
    cast(regime as varchar)                        as regime,
    cast(loss_source as varchar)                   as loss_source,
    cast(pit_loss_s as double)                     as pit_loss_s,
    cast(position_now as integer)                  as position_now,
    cast(predicted_position as integer)            as predicted_position,
    cast(predicted_position_fast as integer)       as predicted_position_fast,
    cast(predicted_position_slow as integer)       as predicted_position_slow,
    cast(predicted_position_global as integer)     as predicted_position_global,
    cast(margin_s as double)                       as margin_s,
    cast(actual_position as integer)               as actual_position,
    cast(other_stops_nearby as integer)            as other_stops_nearby,
    cast(predicted_position - actual_position as integer) as error,
    cast(actual_position between predicted_position_fast and predicted_position_slow as boolean) as in_range,
    cast(case when margin_s is null then null
              when margin_s < 1 then 'under 1 s'
              when margin_s < 3 then '1 to 3 s'
              else 'over 3 s' end as varchar)      as margin_bucket
from joined
