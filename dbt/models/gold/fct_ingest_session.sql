-- One row per session (year, round, code) that appears in the ingest log.
-- ever_ok follows batch.py: a session counts as loaded once any ingest run for it ended ok.
-- Rows per table come from the latest run that wrote that table, so a backfill of track_status shows up here.
-- A table error is only reported while no run has written the table.
with runs as (

    select * from {{ ref('silver_ingest_runs') }} where session_key is not null

),

agg as (

    select
        session_key,
        year,
        round,
        session_code,
        count(*)                                                                    as n_runs,
        count(*) filter (where run_source = 'backfill')                             as n_backfill_runs,
        min(ran_at)                                                                 as first_ran_at,
        max(ran_at)                                                                 as last_ran_at,
        coalesce(bool_or(status = 'ok') filter (where run_source = 'ingest'), false) as ever_ok,
        arg_max(status, ran_at) filter (where run_source = 'ingest')                as latest_status,
        coalesce(bool_or(with_telemetry) filter (where run_source = 'ingest'), false) as with_telemetry,
        sum(seconds)                                                                as total_seconds
        {%- for t in ['laps', 'weather', 'race_control', 'results', 'track_status', 'session_status'] %},
        arg_max({{ t }}_rows, ran_at) filter (where {{ t }}_rows is not null)       as {{ t }}_rows,
        arg_max({{ t }}_error, ran_at) filter (where {{ t }}_error is not null)     as {{ t }}_last_error
        {%- endfor %}
    from runs
    group by session_key, year, round, session_code

)

select
    session_key, year, round, session_code, n_runs, n_backfill_runs, first_ran_at, last_ran_at,
    ever_ok, latest_status, with_telemetry, total_seconds
    {%- for t in ['laps', 'weather', 'race_control', 'results', 'track_status', 'session_status'] %},
    {{ t }}_rows,
    case when {{ t }}_rows is null then {{ t }}_last_error end                        as {{ t }}_error
    {%- endfor %}
from agg
