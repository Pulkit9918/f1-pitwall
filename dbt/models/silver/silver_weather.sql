-- Silver: typed weather samples. One row per (session, sample time).
-- Units are as delivered by the feed. Wind speed is believed to be m/s (an interpretation of the
-- FastF1 documentation, not verified against these files).
with raw as (

    select
        cast(year as integer)           as year,
        cast(round as integer)          as round,
        cast(session as varchar)        as session_code,
        Time_s                          as time_s,
        AirTemp                         as air_temp,
        TrackTemp                       as track_temp,
        Humidity                        as humidity,
        Pressure                        as pressure,
        coalesce(Rainfall, false)       as is_raining,
        WindSpeed                       as wind_speed,
        cast(WindDirection as integer)  as wind_direction
    from {{ source('lake', 'weather') }}
    where Time_s is not null

)

select
    {{ session_key('year', 'round', 'session_code') }}  as session_key,
    *
from raw
qualify row_number() over (
    partition by year, round, session_code, time_s order by time_s
) = 1
