-- One row per session with weather summary statistics.
select
    session_key,
    year,
    round,
    session_code,
    count(*)                        as samples,
    avg(air_temp)                   as avg_air_temp,
    avg(track_temp)                 as avg_track_temp,
    min(track_temp)                 as min_track_temp,
    max(track_temp)                 as max_track_temp,
    avg(humidity)                   as avg_humidity,
    max(wind_speed)                 as max_wind_speed,
    bool_or(is_raining)             as any_rain,
    avg(is_raining::integer)        as share_of_samples_raining
from {{ ref('silver_weather') }}
group by session_key, year, round, session_code
