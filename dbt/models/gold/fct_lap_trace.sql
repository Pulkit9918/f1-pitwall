-- Every usable lap resampled onto the same grid of var trace_points (default 160) distances from the line to the
-- line, so any two laps can be compared point by point.
-- Distance is the x/y path length (fct_lap_position) scaled so each lap ends at its layout's reference length
-- (dim_layout_length). Time is the time since the lap started at that distance, interpolated between the two
-- position samples either side, so time_s at the last point is the lap time and at the first point is 0. Time against
-- distance never uses the speed channel, so the delta between two laps holds even where the speed channel is bad.
-- Speed, throttle, gear, DRS and brake are looked up from the car telemetry at that time, but only for laps whose
-- speed channel agrees with the positions (speed_ok in fct_lap_trace_lap); otherwise they are null. Speed is
-- interpolated between samples; the other channels hold the value of the sample just before.
-- A lap is here only if fct_lap_trace_lap says has_trace.
with usable as (

    select lap_key, session_key, driver_code, lap_number, lap_elapsed_s, integrated_m, ref_length_m, speed_ok
    from {{ ref('fct_lap_trace_lap') }}
    where has_trace

),

scaled as (

    select
        p.lap_key,
        p.elapsed_s,
        p.dist_m * u.ref_length_m / u.integrated_m as dist_m
    from {{ ref('fct_lap_position') }} as p
    join usable as u on u.lap_key = p.lap_key

),

knots as (

    select
        lap_key, elapsed_s, dist_m,
        lead(elapsed_s) over w as next_t,
        lead(dist_m) over w    as next_d
    from (
        select lap_key, elapsed_s, dist_m from scaled
        union all
        -- the line at the start (distance 0, time 0) and the finish (reference length, lap time), so every grid
        -- distance falls between two known points
        select lap_key, 0.0, 0.0 from usable
        union all
        select lap_key, lap_elapsed_s, ref_length_m from usable
    )
    window w as (partition by lap_key order by dist_m, elapsed_s)

),

grid as (

    select
        u.lap_key, u.session_key, u.driver_code, u.lap_number, u.speed_ok,
        cast(g.i as smallint)                                                as point_idx,
        u.ref_length_m * g.i / ({{ var('trace_points', 160) }} - 1)          as target_m
    from usable as u
    cross join generate_series(0, {{ var('trace_points', 160) }} - 1) as g(i)

),

timed as (

    select
        grid.lap_key, grid.session_key, grid.driver_code, grid.lap_number, grid.speed_ok, grid.point_idx, grid.target_m,
        case
            when grid.point_idx = 0 then 0.0
            when knots.next_d is null or knots.next_d <= knots.dist_m then knots.elapsed_s
            else knots.elapsed_s + (grid.target_m - knots.dist_m) / (knots.next_d - knots.dist_m) * (knots.next_t - knots.elapsed_s)
        end as t
    from grid
    asof join knots
        on grid.lap_key = knots.lap_key
       and grid.target_m >= knots.dist_m

),

car as (

    select
        lap_key, elapsed_s, speed, throttle, gear, drs, brake,
        lead(elapsed_s) over w as next_t,
        lead(speed) over w     as next_speed
    from (
        select s.lap_key, s.elapsed_s, s.speed, s.throttle, s.gear, s.drs, s.brake
        from {{ ref('fct_lap_sample') }} as s
        join usable as u on u.lap_key = s.lap_key and u.speed_ok
        union all
        -- the first sample repeated just before the line, so the first grid points have a value to hold
        select lap_key, -1.0, speed, throttle, gear, drs, brake
        from (
            select s.*, row_number() over (partition by s.lap_key order by s.elapsed_s) as rn
            from {{ ref('fct_lap_sample') }} as s
            join usable as u on u.lap_key = s.lap_key and u.speed_ok
        ) where rn = 1
    )
    window w as (partition by lap_key order by elapsed_s)

)

select
    timed.lap_key,
    timed.session_key,
    timed.driver_code,
    cast(timed.lap_number as integer)                                                   as lap_number,
    timed.point_idx,
    cast(timed.target_m as real)                                                        as dist_m,
    cast(timed.t as real)                                                               as time_s,
    cast(round(case when car.next_t is null or car.next_t <= car.elapsed_s then car.speed
                    else car.speed + (timed.t - car.elapsed_s) / (car.next_t - car.elapsed_s) * (car.next_speed - car.speed)
               end) as smallint)                                                        as speed_kph,
    car.throttle                                                                        as throttle_pct,
    car.gear                                                                            as gear,
    car.drs                                                                             as drs,
    car.brake                                                                           as brake
from timed
asof left join car
    on timed.lap_key = car.lap_key
   and timed.t >= car.elapsed_s
