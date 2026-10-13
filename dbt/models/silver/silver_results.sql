-- Silver: typed, deduplicated session results. One row per (session, driver code).
with raw as (

    select
        cast(year as integer)               as year,
        cast(round as integer)              as round,
        cast(session as varchar)            as session_code,
        event,
        cast(DriverNumber as varchar)       as driver_number,
        cast(Abbreviation as varchar)       as driver_code,
        DriverId                            as driver_id,
        FullName                            as full_name,
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

)

select
    {{ session_key('year', 'round', 'session_code') }}  as session_key,
    *
from raw
qualify row_number() over (
    partition by year, round, session_code, driver_code
    order by position asc nulls last
) = 1
