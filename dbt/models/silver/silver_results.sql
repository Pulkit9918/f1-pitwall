-- Silver: typed, deduplicated session results. One row per (session, driver code).
-- FastF1 sometimes has no DriverId ('nan' or blank), mostly for practice-only drivers. It is then resolved:
--   1. jolpica_season : same season and 3-letter code in the Jolpica history, when the code maps to one driver
--   2. jolpica_any    : the code maps to exactly one driver across all seasons
--   3. surrogate      : 'ff1-<code>' (a driver who has never raced has no id anywhere else)
-- driver_id_source records which. FastF1 writes missing names as the text 'None None'; those become null.
with hist_season as (

    select season, driver_code, min(driver_id) as driver_id
    from {{ ref('silver_history_results') }}
    where driver_code is not null and driver_id is not null
    group by season, driver_code
    having count(distinct driver_id) = 1

),

hist_any as (

    select driver_code, min(driver_id) as driver_id
    from {{ ref('silver_history_results') }}
    where driver_code is not null and driver_id is not null
    group by driver_code
    having count(distinct driver_id) = 1

),

raw as (

    select
        cast(year as integer)               as year,
        cast(round as integer)              as round,
        cast(session as varchar)            as session_code,
        event,
        cast(DriverNumber as varchar)       as driver_number,
        cast(Abbreviation as varchar)       as driver_code,
        DriverId                            as driver_id,
        nullif(trim(FullName), 'None None') as full_name,
        CountryCode                         as country_code,
        TeamName                            as team_name,
        TeamId                              as team_id,
        cast(Position as integer)           as position,
        ClassifiedPosition                  as classified_position,
        cast(GridPosition as integer)       as grid_position,
        Status                              as status,
        Points                              as points,
        cast(Laps as integer)               as laps_completed,
        Q1_s                                as q1_s,
        Q2_s                                as q2_s,
        Q3_s                                as q3_s,
        Time_s                              as time_s
    from {{ source('lake', 'results') }}
    where Abbreviation is not null

),

resolved as (

    select
        raw.* exclude (driver_id),
        case
            when raw.driver_id is not null and lower(trim(raw.driver_id)) not in ('', 'nan') then raw.driver_id
            when hs.driver_id is not null then hs.driver_id
            when ha.driver_id is not null then ha.driver_id
            else 'ff1-' || lower(raw.driver_code)
        end                                 as driver_id,
        case
            when raw.driver_id is not null and lower(trim(raw.driver_id)) not in ('', 'nan') then 'fastf1'
            when hs.driver_id is not null then 'jolpica_season'
            when ha.driver_id is not null then 'jolpica_any'
            else 'surrogate'
        end                                 as driver_id_source
    from raw
    left join hist_season hs
        on hs.season = raw.year
       and hs.driver_code = raw.driver_code
    left join hist_any ha
        on ha.driver_code = raw.driver_code

)

select
    {{ session_key('year', 'round', 'session_code') }}  as session_key,
    *
from resolved
qualify row_number() over (
    partition by year, round, session_code, driver_code
    order by position asc nulls last
) = 1
