-- One row per driver per race, 1950 to now (Jolpica). A driver who shared or switched cars in one
-- race can appear more than once; the key includes the constructor, and a test warns if it is still not unique.
select
    season || '-' || lpad(cast(round as varchar), 2, '0')                            as race_key,
    season || '-' || lpad(cast(round as varchar), 2, '0') || '-' || driver_id
        || '-' || coalesce(constructor_id, '')                                       as result_key,
    season,
    round,
    race_name,
    race_date,
    circuit_id,
    driver_id,
    driver_code,
    constructor_id,
    grid,
    position,
    points,
    laps,
    status,
    time_ms,
    fastest_rank,
    coalesce(position = 1, false)                                                     as is_win,
    coalesce(position <= 3, false)                                                    as is_podium,
    coalesce(status = 'Finished' or status like '+%', false)                          as is_classified_finish
from {{ ref('silver_history_results') }}
