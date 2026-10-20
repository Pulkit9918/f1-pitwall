{{ config(severity='warn') }}
-- Sessions where telemetry is missing, ends early, starts late or is thin (see rec_telemetry_coverage).
select session_key, year, round, session_code, telemetry_missing, ends_early, starts_late, thin
from {{ ref('rec_telemetry_coverage') }}
where has_issue
