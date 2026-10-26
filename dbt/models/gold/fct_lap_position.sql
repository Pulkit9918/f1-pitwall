{{ config(materialized='view') }}
-- One row per position update (x, y) inside a race, sprint or qualifying lap, from the year in var trace_from_year. A sample whose
-- position is the same as the one before it is dropped: some sessions repeat each position for several samples and
-- then jump, which would otherwise look like a well-sampled lap and cut every corner. Gaps are therefore measured
-- between real updates, and a session like that fails the gap test in fct_lap_trace_lap.
-- dist_m is the distance covered since the lap started, in metres: the length of the x/y path up to the sample (the
-- positions are in tenths of a metre), plus the stretch before the first sample, covered at the rate of the first
-- step. This is the distance axis for fct_lap_trace; unlike the speed channel it does not drift or stick.
-- Samples are matched to laps by driver code and session clock (same clock as fct_lap.lap_start_time_s).
-- A sample at (0, 0) is a missing position and is dropped, as in the replay export. It is a view (the rows are many
-- and recomputing them takes seconds), so it does not add to the size of the database.
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

pos as (

    select
        cast(year as integer)             as year,
        cast(round as integer)            as round,
        cast(session as varchar)          as session_code,
        cast(driver_number as varchar)    as driver_number,
        cast(session_time_s as double)    as t_s,
        cast(x as double)                 as x,
        cast(y as double)                 as y
    from {{ source('lake', 'telemetry_pos') }}
    where session in ('R', 'S', 'Q', 'SQ', 'SS')
      and year >= {{ var('trace_from_year', 2024) }}
      and session_time_s is not null
      and x is not null
      and y is not null
      and not (x = 0 and y = 0)

),

coded as (

    select
        {{ session_key('year', 'round', 'session_code') }} as session_key,
        driver_number, t_s, x, y
    from pos

),

named as (

    select coded.session_key, numbers.driver_code, coded.t_s, coded.x, coded.y
    from coded
    join numbers
        on numbers.session_key = coded.session_key
       and numbers.driver_number = coded.driver_number

),

cut as (

    select laps.lap_key, laps.start_s, named.t_s, named.x, named.y
    from named
    asof join laps
        on named.session_key = laps.session_key
       and named.driver_code = laps.driver_code
       and named.t_s >= laps.start_s
    where named.t_s <= laps.end_s

),

changed as (

    select lap_key, start_s, t_s, x, y
    from (
        select
            lap_key, start_s, t_s, x, y,
            lag(x) over w as last_x,
            lag(y) over w as last_y
        from cut
        window w as (partition by lap_key order by t_s)
    )
    where last_x is null or x <> last_x or y <> last_y

),

stepped as (

    select
        lap_key, start_s, t_s, x, y,
        lag(t_s) over w  as prev_t,
        lag(x) over w    as prev_x,
        lag(y) over w    as prev_y,
        lead(t_s) over w as next_t,
        lead(x) over w   as next_x,
        lead(y) over w   as next_y
    from changed
    window w as (partition by lap_key order by t_s)

),

rated as (

    select
        lap_key, start_s, t_s, prev_t,
        case when prev_t is null then 0.0 else sqrt(power(x - prev_x, 2) + power(y - prev_y, 2)) / 10.0 end as step_m,
        case when prev_t is null or t_s <= prev_t then null
             else sqrt(power(x - prev_x, 2) + power(y - prev_y, 2)) / 10.0 / (t_s - prev_t) end             as rate_mps,
        case when next_t is null or next_t <= t_s then null
             else sqrt(power(next_x - x, 2) + power(next_y - y, 2)) / 10.0 / (next_t - t_s) end             as rate_fwd_mps
    from stepped

)

select
    lap_key,
    cast(t_s - start_s as double)                                                                   as elapsed_s,
    cast(t_s - coalesce(prev_t, start_s) as double)                                                 as gap_s,
    cast(
        coalesce(first_value(rate_fwd_mps) over w, 0.0) * (first_value(t_s) over w - start_s)
        + sum(step_m) over (partition by lap_key order by t_s rows between unbounded preceding and current row)
    as double)                                                                                       as dist_m,
    cast(rate_mps as double)                                                                         as rate_mps
from rated
window w as (partition by lap_key order by t_s)
