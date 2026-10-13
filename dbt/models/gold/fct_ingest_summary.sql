-- One row per year: how much is loaded and how recently. Meant for a quick look and for freshness checks.
select
    year,
    count(*)                                                       as sessions_in_log,
    count(*) filter (where ever_ok)                                as sessions_loaded,
    count(*) filter (where not ever_ok)                            as sessions_not_loaded,
    count(*) filter (where with_telemetry)                         as sessions_with_telemetry,
    min(first_ran_at)                                              as first_ran_at,
    max(last_ran_at)                                               as last_ran_at,
    cast(sum(total_seconds) / 3600.0 as double)                    as hours_spent
from {{ ref('fct_ingest_session') }}
group by year
