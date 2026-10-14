{{ config(severity='warn') }}
-- A race weekend with at least one loaded session but an expected session missing, or loaded without laps. Years up to the current
-- year only. A weekend that is still in progress shows up here until its last session is ingested.
select c.session_key, c.year, c.round, c.session_code, c.weekend_format, c.weekend_sessions_loaded,
       c.is_loaded, coalesce(d.has_laps, false) as has_laps
from {{ ref('rec_weekend_coverage') }} c
left join {{ ref('dim_session') }} d using (session_key)
where (not c.is_loaded or not coalesce(d.has_laps, false))
  and c.weekend_sessions_loaded > 0
  and c.year <= extract(year from current_date)
