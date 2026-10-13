-- For each lake table: rows in the Parquet files (per session) against the rows the ingest log says were written.
-- check_result: match | row_mismatch | missing_in_lake (log says written, no files) | not_in_manifest (files, no log).
-- A zero-row table has no rows to count, so a logged 0 against no rows in the lake counts as a match.
-- Telemetry tables are not covered here. Raw counts on both sides, so duplicates are included in both.
{%- set tables = ['laps', 'weather', 'race_control', 'results', 'track_status'] %}
with lake as (

    {%- for t in tables %}
    select '{{ t }}' as table_name, cast(year as integer) as year, cast(round as integer) as round,
           cast(session as varchar) as session_code, count(*) as lake_rows
    from {{ source('lake', t) }}
    group by all
    {% if not loop.last %}union all{% endif %}
    {%- endfor %}

),

manifest as (

    {%- for t in tables %}
    select '{{ t }}' as table_name, year, round, session_code, {{ t }}_rows as manifest_rows
    from {{ ref('fct_ingest_session') }}
    where {{ t }}_rows is not null
    {% if not loop.last %}union all{% endif %}
    {%- endfor %}

)

select
    coalesce(l.table_name, m.table_name)       as table_name,
    coalesce(l.year, m.year)                   as year,
    coalesce(l.round, m.round)                 as round,
    coalesce(l.session_code, m.session_code)   as session_code,
    l.lake_rows,
    m.manifest_rows,
    case
        when l.lake_rows is null and m.manifest_rows = 0 then 'match'
        when l.lake_rows is null then 'missing_in_lake'
        when m.manifest_rows is null then 'not_in_manifest'
        when l.lake_rows = m.manifest_rows then 'match'
        else 'row_mismatch'
    end                                        as check_result
from lake l
full outer join manifest m
    on l.table_name = m.table_name
   and l.year = m.year
   and l.round = m.round
   and l.session_code = m.session_code
