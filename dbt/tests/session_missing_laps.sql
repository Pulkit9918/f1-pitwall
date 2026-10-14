{{ config(severity='warn') }}
-- Races, qualifying and sprint sessions that have an official result but no laps at all.
-- Expected today: one row, the 2018 Italian GP race, for which FastF1 cannot load timing data
-- (see README, known data gaps). Any new row is a session to investigate.
select session_key, event, has_laps, has_results
from {{ ref('dim_session') }}
where has_results
  and not has_laps
  and session_code in ('R', 'Q', 'S', 'SQ', 'SS')
