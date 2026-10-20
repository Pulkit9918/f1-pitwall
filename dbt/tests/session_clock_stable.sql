{{ config(severity='warn') }}
-- A session whose laps disagree about when second zero was (p90 minus p10 over 1 s) has an unreliable clock.
select session_key, spread_s, laps_used
from {{ ref('silver_session_clock') }}
where spread_s > 1
