{{ config(severity='warn') }}
-- A race weekend with at least one loaded session but an expected session missing. Years up to the current
-- year only. A weekend that is still in progress shows up here until its last session is ingested.
select session_key, year, round, session_code, weekend_format, weekend_sessions_loaded
from {{ ref('rec_weekend_coverage') }}
where not is_loaded
  and weekend_sessions_loaded > 0
  and year <= extract(year from current_date)
