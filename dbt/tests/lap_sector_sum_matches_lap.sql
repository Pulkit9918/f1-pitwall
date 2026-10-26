{{ config(severity='warn') }}
-- A lap with all three sectors timed should have sectors that add up to its lap time. More than 0.05 s apart means one
-- of the sector times or the lap time is wrong, so the colours for that lap cannot be trusted.
select l.lap_key, l.sector1_s + l.sector2_s + l.sector3_s as sectors_s, l.lap_time_s
from {{ ref('fct_lap') }} as l
where not coalesce(l.deleted, false)
  and l.sector1_s > 0 and l.sector2_s > 0 and l.sector3_s > 0
  and l.lap_time_s is not null
  and abs(l.sector1_s + l.sector2_s + l.sector3_s - l.lap_time_s) > 0.05
