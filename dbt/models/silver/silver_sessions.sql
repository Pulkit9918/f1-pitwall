-- Silver: every session that appears in any source table, with flags for what exists.
with u as (

    select session_key, year, round, session_code, event, 'laps' as src from {{ ref('silver_laps') }}
    union all
    select session_key, year, round, session_code, event, 'results' as src from {{ ref('silver_results') }}
    union all
    select session_key, year, round, session_code, event, 'race_control' as src from {{ ref('silver_race_control') }}

)

select
    session_key,
    year,
    round,
    session_code,
    max(event)                          as event,
    bool_or(src = 'laps')               as has_laps,
    bool_or(src = 'results')            as has_results,
    bool_or(src = 'race_control')       as has_race_control
from u
group by session_key, year, round, session_code
