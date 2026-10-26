-- Every lap in fct_lap_trace has exactly trace_points points, starts at distance 0 and time 0, never goes backwards
-- in distance or time, and its last point is the lap time (to 5 ms) at the layout's reference length.
-- Returns the laps that break any of these.
with per_lap as (

    select
        t.lap_key,
        count(*)                                    as points,
        min(t.dist_m)                               as first_dist,
        min(t.time_s)                               as first_time,
        max(t.dist_m)                               as last_dist,
        max(t.time_s)                               as last_time,
        sum(case when t.time_s < lag_time or t.dist_m < lag_dist then 1 else 0 end) as backwards
    from (
        select
            lap_key, point_idx, dist_m, time_s,
            lag(time_s) over w as lag_time,
            lag(dist_m) over w as lag_dist
        from {{ ref('fct_lap_trace') }}
        window w as (partition by lap_key order by point_idx)
    ) as t
    group by t.lap_key

)

select
    p.lap_key, p.points, p.first_dist, p.first_time, p.last_dist, p.last_time, p.backwards, l.lap_elapsed_s, l.ref_length_m
from per_lap as p
join {{ ref('fct_lap_trace_lap') }} as l on l.lap_key = p.lap_key
where p.points <> {{ var('trace_points', 160) }}
   or p.first_dist <> 0
   or p.first_time <> 0
   or p.backwards > 0
   or abs(p.last_time - l.lap_elapsed_s) > 0.005
   or abs(p.last_dist - l.ref_length_m) > 0.5
