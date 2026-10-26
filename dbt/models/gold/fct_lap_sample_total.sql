-- Per lap that has position data: the distance its x/y path adds up to, and how well the samples cover the lap.
-- integrated_m is the path length over the whole lap, with the stretch after the last sample covered at the rate of
-- the last step. first_gap_s and last_gap_s are how far the first sample is after the lap start and the last one
-- before the lap end; max_gap_s is the longest silence between samples, counting the first gap.
-- car_integrated_m is the same lap's speed integral from the car telemetry (null when it has none), kept to check
-- whether the speed channel agrees with the positions.
with pos as (

    select
        lap_key,
        count(*)                         as n_samples,
        min(elapsed_s)                   as first_gap_s,
        max(gap_s)                       as max_gap_s,
        max(elapsed_s)                   as last_elapsed_s,
        max(dist_m)                      as sampled_m,
        arg_max(rate_mps, elapsed_s)     as last_rate_mps
    from {{ ref('fct_lap_position') }}
    group by lap_key

),

car as (

    select
        lap_key,
        max(dist_m) as sampled_m,
        max(elapsed_s)                   as last_elapsed_s,
        arg_max(speed, elapsed_s)        as last_speed
    from {{ ref('fct_lap_sample') }}
    group by lap_key

)

select
    pos.lap_key,
    l.session_key,
    pos.n_samples,
    l.time_s - l.lap_start_time_s                                                                       as lap_elapsed_s,
    pos.first_gap_s,
    l.time_s - l.lap_start_time_s - pos.last_elapsed_s                                                  as last_gap_s,
    pos.max_gap_s,
    pos.sampled_m + coalesce(pos.last_rate_mps, 0.0) * (l.time_s - l.lap_start_time_s - pos.last_elapsed_s) as integrated_m,
    car.sampled_m + coalesce(car.last_speed, 0) / 3.6 * (l.time_s - l.lap_start_time_s - car.last_elapsed_s) as car_integrated_m
from pos
join {{ ref('fct_lap') }} as l on l.lap_key = pos.lap_key
left join car on car.lap_key = pos.lap_key
