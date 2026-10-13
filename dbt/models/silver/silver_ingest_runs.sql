-- Silver: the ingest log, typed. One row per ingest or backfill attempt (sessions.jsonl and backfill.jsonl).
-- rows written per table come from the tables field; a table that failed has a *_error text instead.
-- round is missing on runs that failed before the event was known: it then falls back to the requested round.
with raw as (

    select
        filename                                                                       as manifest_file,
        case when filename like '%backfill.jsonl' then 'backfill' else 'ingest' end    as run_source,
        cast(year as integer)                                                          as year,
        coalesce(cast(round as integer), try_cast(requested_event as integer))         as round,
        cast(session as varchar)                                                       as session_code,
        status,
        error,
        timezone('UTC', try_cast(coalesce(ingested_at, "at") as timestamptz))          as ran_at,
        coalesce(with_telemetry, false)                                                as with_telemetry,
        seconds,
        {%- for t in ['laps', 'weather', 'race_control', 'results', 'track_status', 'session_status'] %}
        try_cast(json_extract(tables, '$.{{ t }}.rows') as bigint)                     as {{ t }}_rows,
        json_extract_string(tables, '$.{{ t }}.error')                                 as {{ t }}_error,
        {%- endfor %}
        tables is not null                                                             as has_tables
    from {{ source('manifest', 'runs') }}

)

select
    case when round is not null then {{ session_key('year', 'round', 'session_code') }} end as session_key,
    *
from raw
