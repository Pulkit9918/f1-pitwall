{{ config(materialized='view') }}
-- One row per car-telemetry sample (speed, throttle, gear, DRS, brake) that falls inside a race, sprint or qualifying lap, from the
-- year in var trace_from_year (default 2024; widen it to cover more seasons, at the cost of build time and database size).
-- Samples are matched to laps by driver code and session clock: telemetry session_time_s is on the same clock as
-- fct_lap.lap_start_time_s, and a sample belongs to the lap that started most recently at or before it.
-- dist_m is speed integrated over the lap (trapezoid rule). It is NOT used as the distance axis, because the speed
-- channel is unreliable lap to lap (stuck values, drift); the position data gives the distance (fct_lap_position).
-- It is a view (the rows are many and recomputing them takes seconds), so it adds nothing to the size of the database.
-- It is kept as a check: fct_lap_trace_lap compares it with the position distance to decide whether a lap's speed
-- channel can be trusted.
with numbers as (

    select session_key, driver_number, min(driver_code) as driver_code
    from {{ ref('silver_results') }}
    where driver_number is not null and driver_code is not null
    group by session_key, driver_number
    having count(distinct driver_code) = 1

),

laps as (

    select
        session_key,
        lap_key,
        driver_code,
        lap_start_time_s as start_s,
        time_s           as end_s
    from {{ ref('fct_lap') }}
    where session_code in ('R', 'S', 'Q', 'SQ', 'SS')
      and year >= {{ var('trace_from_year', 2024) }}
      and lap_start_time_s is not null
      and time_s is not null
      and time_s > lap_start_time_s

),

car as (

    select
        cast(year as integer)             as year,
        cast(round as integer)            as round,
        cast(session as varchar)          as session_code,
        cast(driver_number as varchar)    as driver_number,
        cast(session_time_s as double)    as t_s,
        cast(speed as smallint)           as speed,
        cast(throttle as smallint)        as throttle,
        cast(ngear as smallint)           as gear,
        cast(drs as smallint)             as drs,
        coalesce(brake, false)            as brake
    from {{ source('lake', 'telemetry_car') }}
    where session in ('R', 'S', 'Q', 'SQ', 'SS')
      and year >= {{ var('trace_from_year', 2024) }}
      and session_time_s is not null
      and speed is not null

),

coded as (

    select
        {{ session_key('year', 'round', 'session_code') }} as session_key,
        driver_number, t_s, speed, throttle, gear, drs, brake
    from car

),

named as (

    select coded.session_key, numbers.driver_code, coded.t_s, coded.speed, coded.throttle, coded.gear, coded.drs, coded.brake
    from coded
    join numbers
        on numbers.session_key = coded.session_key
       and numbers.driver_number = coded.driver_number

),

cut as (

    select
        laps.lap_key, laps.start_s, named.t_s, named.speed, named.throttle, named.gear, named.drs, named.brake
    from named
    asof join laps
        on named.session_key = laps.session_key
       and named.driver_code = laps.driver_code
       and named.t_s >= laps.start_s
    where named.t_s <= laps.end_s

),

stepped as (

    select
        lap_key, start_s, t_s, speed, throttle, gear, drs, brake,
        lag(t_s) over w     as prev_t,
        lag(speed) over w   as prev_speed
    from cut
    window w as (partition by lap_key order by t_s)

),

increments as (

    select
        lap_key, t_s, start_s, speed, throttle, gear, drs, brake, prev_t,
        case
            when prev_t is null then speed / 3.6 * (t_s - start_s)
            else (speed + prev_speed) / 7.2 * (t_s - prev_t)
        end as step_m
    from stepped

)

select
    lap_key,
    cast(t_s - start_s as double)                                                                    as elapsed_s,
    cast(t_s - coalesce(prev_t, start_s) as double)                                                  as gap_s,
    cast(sum(step_m) over (partition by lap_key order by t_s rows between unbounded preceding and current row) as double) as dist_m,
    speed,
    throttle,
    gear,
    drs,
    brake
from increments
