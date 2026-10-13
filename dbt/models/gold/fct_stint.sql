-- One row per driver stint (a run on one set of tyres), with clean-lap pace.
select
    session_key || '-' || driver_code || '-S' || cast(stint as varchar)     as stint_key,
    session_key,
    year,
    round,
    session_code,
    driver_code,
    any_value(driver_id)                                                    as driver_id,
    stint,
    arg_min(compound, lap_number)                                           as compound,
    min(lap_number)                                                         as start_lap,
    max(lap_number)                                                         as end_lap,
    count(*)                                                                as laps,
    min(tyre_life)                                                          as tyre_life_start,
    max(tyre_life)                                                          as tyre_life_end,
    count(*) filter (where is_clean_lap)                                    as clean_laps,
    median(lap_time_s) filter (where is_clean_lap)                          as median_clean_lap_s,
    avg(lap_time_s) filter (where is_clean_lap)                             as mean_clean_lap_s
from {{ ref('fct_lap') }}
where stint is not null
group by session_key, year, round, session_code, driver_code, stint
