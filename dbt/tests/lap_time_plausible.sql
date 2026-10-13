{{ config(severity='warn') }}
-- Laps outside 20 s to 600 s are almost certainly timing glitches. Warns, does not fail the build.
select lap_key, session_key, driver_code, lap_time_s
from {{ ref('fct_lap') }}
where lap_time_s is not null
  and coalesce(track_status, '') not like '%5%'   -- red-flag laps can be very long
  and (lap_time_s < 20 or lap_time_s > 600)
