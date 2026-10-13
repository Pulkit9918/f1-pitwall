{{ config(severity='warn') }}
-- Lake files and the ingest log disagree: different row counts, files the log never recorded, or a log entry
-- with no files. A warning to investigate (a manual delete, an interrupted run, a re-ingest).
select table_name, year, round, session_code, lake_rows, manifest_rows, check_result
from {{ ref('rec_lake_vs_manifest') }}
where check_result <> 'match'
