-- One row per driver per lap of a race or sprint: the gap to the leader, the interval to the car ahead and the
-- gap to the car behind, all measured where the lap ends (the timing line), from the session clock at the end of
-- each lap in fct_lap.
--
--   gap_to_leader_s = this car's lap-end time minus the leader's lap-end time for the same lap number
--   interval_s      = this car's lap-end time minus the lap-end time of the car in the position directly ahead
--   gap_behind_s    = the lap-end time of the car directly behind minus this car's
--
-- Order comes from fct_lap.position (the order recorded at the end of the lap). A value that would be negative
-- means the recorded order disagrees with the clock for that lap; it is left null and flagged, not repaired.
-- A car that is a lap or more down is compared by lap number, so its gap can exceed one lap time:
-- is_lapped marks gaps longer than the leader's lap time. These are gaps at the line once per lap, not
-- continuous timing, and they say nothing about what happened inside a lap.
with base as (
    select
        session_key, lap_key, year, round, session_code, driver_code, lap_number,
        position, time_s, lap_time_s, track_status
    from {{ ref('fct_lap') }}
    where session_code in ('R', 'S')
      and time_s is not null
      and position is not null
),

by_position as (
    select
        session_key, lap_number, position,
        min(time_s)                    as pos_time_s,
        arg_min(driver_code, time_s)   as pos_driver
    from base
    group by session_key, lap_number, position
),

leader_lap as (
    select session_key, lap_number, min(lap_time_s) as leader_lap_time_s
    from base where position = 1 group by session_key, lap_number
),

joined as (
    select
        b.*,
        l.pos_time_s  as leader_time_s,
        ll.leader_lap_time_s,
        a.pos_time_s  as ahead_time_s,
        a.pos_driver  as car_ahead_code,
        k.pos_time_s  as behind_time_s,
        k.pos_driver  as car_behind_code
    from base b
    left join by_position l  on l.session_key = b.session_key and l.lap_number = b.lap_number and l.position = 1
    left join leader_lap ll  on ll.session_key = b.session_key and ll.lap_number = b.lap_number
    left join by_position a  on a.session_key = b.session_key and a.lap_number = b.lap_number and a.position = b.position - 1
    left join by_position k  on k.session_key = b.session_key and k.lap_number = b.lap_number and k.position = b.position + 1
)

select
    lap_key,
    session_key,
    cast(year as integer)                                                    as year,
    cast(round as integer)                                                   as round,
    session_code,
    driver_code,
    cast(lap_number as integer)                                              as lap_number,
    cast(position as integer)                                                as position,
    cast(time_s as double)                                                   as time_s,
    track_status,
    case when position = 1 then 0.0
         when time_s - leader_time_s >= 0 then cast(time_s - leader_time_s as double) end   as gap_to_leader_s,
    car_ahead_code,
    case when ahead_time_s is not null and time_s - ahead_time_s >= 0
         then cast(time_s - ahead_time_s as double) end                      as interval_s,
    car_behind_code,
    case when behind_time_s is not null and behind_time_s - time_s >= 0
         then cast(behind_time_s - time_s as double) end                     as gap_behind_s,
    coalesce(time_s - leader_time_s > leader_lap_time_s, false)              as is_lapped,
    coalesce(
        (position > 1 and (time_s - leader_time_s < 0 or time_s - ahead_time_s < 0))
        or (behind_time_s is not null and behind_time_s - time_s < 0),
        false)                                                               as order_disagrees_with_clock
from joined
