-- One row per driver per race, 1950 to now (Jolpica).
-- In the early years a driver could take over a second car in the same race (a shared drive), which gives two
-- rows for the same driver and constructor. drive_number numbers them 1, 2, ... (best finish first) and the
-- key gets a -2, -3 suffix for the extra drives, so result_key is unique.
with base as (

    select
        *,
        row_number() over (
            partition by season, round, driver_id, coalesce(constructor_id, '')
            order by position asc nulls last, grid asc nulls last, laps desc nulls last, status
        ) as drive_number
    from {{ ref('silver_history_results') }}

)

select
    season || '-' || lpad(cast(round as varchar), 2, '0')                            as race_key,
    season || '-' || lpad(cast(round as varchar), 2, '0') || '-' || driver_id
        || '-' || coalesce(constructor_id, '')
        || case when drive_number > 1 then '-' || drive_number else '' end           as result_key,
    cast(drive_number as integer)                                                     as drive_number,
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
from base
