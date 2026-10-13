-- Race weekends from coverage_from_year (default 2022) on: which of the expected sessions are loaded.
-- Expected sessions by format (my reading of the FastF1 session names, to be checked against real weekends):
--   conventional    FP1, FP2, FP3, Q, R
--   sprint, 2022    FP1, Q, FP2, S, R
--   sprint, 2023    FP1, Q, SS, S, R   (the Sprint Shootout is stored as SS)
--   sprint, 2024 on FP1, SQ, S, Q, R
-- A weekend counts as a sprint weekend when an S, SS or SQ session of it is in the log.
-- 2018 to 2021 are loaded as R and Q only on purpose, so they are not part of this check.
with loaded as (

    select year, round, session_code, bool_or(ever_ok) as is_loaded
    from {{ ref('fct_ingest_session') }}
    where year >= {{ var('coverage_from_year', 2022) }}
    group by all

),

weekend as (

    select
        year, round,
        bool_or(session_code in ('S', 'SS', 'SQ'))     as is_sprint,
        count(*) filter (where is_loaded)        as sessions_loaded
    from loaded
    group by all

),

expected as (

    select * from (values
        ('conventional', 'FP1'), ('conventional', 'FP2'), ('conventional', 'FP3'),
        ('conventional', 'Q'), ('conventional', 'R'),
        ('sprint_2022', 'FP1'), ('sprint_2022', 'Q'), ('sprint_2022', 'FP2'), ('sprint_2022', 'S'), ('sprint_2022', 'R'),
        ('sprint_2023', 'FP1'), ('sprint_2023', 'Q'), ('sprint_2023', 'SS'), ('sprint_2023', 'S'), ('sprint_2023', 'R'),
        ('sprint_2024', 'FP1'), ('sprint_2024', 'SQ'), ('sprint_2024', 'S'), ('sprint_2024', 'Q'), ('sprint_2024', 'R')
    ) as t(format_code, session_code)

)

select
    {{ session_key('w.year', 'w.round', 'e.session_code') }}  as session_key,
    w.year,
    w.round,
    e.session_code,
    case when w.is_sprint then 'sprint' else 'conventional' end as weekend_format,
    coalesce(l.is_loaded, false)                               as is_loaded,
    w.sessions_loaded                                          as weekend_sessions_loaded
from weekend w
join expected e
    on e.format_code = case
        when not w.is_sprint then 'conventional'
        when w.year = 2022 then 'sprint_2022'
        when w.year = 2023 then 'sprint_2023'
        else 'sprint_2024'
    end
left join loaded l
    on l.year = w.year and l.round = w.round and l.session_code = e.session_code
