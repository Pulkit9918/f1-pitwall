-- One row per pit-lane visit: the in-lap joined to the following out-lap.
-- In races and sprints (is_race_session) a visit is a pit stop. In qualifying and practice it is a
-- garage visit between runs, which can last many minutes; filter on is_race_session for stops.
-- pit_lane_time_s is the time from pit-lane entry to pit-lane exit as timed by the feed.
-- It is NOT the "pit loss" used in the strategy models (which compares two laps with the field's pace).
with in_laps as (
    select * from {{ ref('fct_lap') }} where pit_in_time_s is not null
),

out_laps as (
    select * from {{ ref('fct_lap') }} where pit_out_time_s is not null
)

select
    cast(i.lap_key as varchar)                                  as pit_stop_key,
    cast(i.session_key as varchar)                              as session_key,
    cast(i.driver_code as varchar)                              as driver_code,
    cast(i.driver_id as varchar)                                as driver_id,
    cast(i.lap_number as integer)                               as in_lap,
    cast(i.pit_in_time_s as double)                             as pit_in_time_s,
    cast(o.pit_out_time_s as double)                            as pit_out_time_s,
    cast(o.pit_out_time_s - i.pit_in_time_s as double)          as pit_lane_time_s,
    cast(i.compound as varchar)                                 as compound_before,
    cast(o.compound as varchar)                                 as compound_after,
    cast(i.track_status as varchar)                             as in_lap_track_status,
    cast(o.track_status as varchar)                             as out_lap_track_status,
    cast(coalesce(i.is_green and o.is_green, false) as boolean) as is_green_stop,
    cast(i.position as integer)                                 as position_before,
    cast(i.session_code as varchar)                             as session_code,
    cast(i.session_code in ('R', 'S') as boolean)               as is_race_session
from in_laps i
left join out_laps o
    on  o.session_key = i.session_key
    and o.driver_code = i.driver_code
    and o.lap_number  = i.lap_number + 1
