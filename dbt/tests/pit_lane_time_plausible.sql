{{ config(severity='warn') }}
-- Green-flag stops with a lane time under 5 s or over 300 s. Warns, does not fail the build.
select pit_stop_key, session_key, driver_code, pit_lane_time_s
from {{ ref('fct_pit_stop') }}
where is_green_stop
  and is_race_session
  and pit_lane_time_s is not null
  and (pit_lane_time_s < 5 or pit_lane_time_s > 300)
