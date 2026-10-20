-- Telemetry coverage per session, from 2022 on (the seasons that can have telemetry), checked against the laps table.
-- Telemetry is expected for every session except practice: in the lake all 269 non-practice sessions have both
-- tables and no practice session has either (experiments/telemetry_probe2.py).
-- The flags use two tolerances, set just outside the range seen in the lake: telemetry may end up to
-- telemetry_end_tolerance_s before the last lap ends (seen: 10 s at worst, apart from one truncated session),
-- and a session is thin below telemetry_min_rate_hz samples per driver per second (seen: 3.17 and above, apart
-- from the same session).
with laps as (
    select
        session_key, year, round, session_code,
        count(distinct driver_code)  as laps_drivers,
        min(lap_start_time_s)        as first_lap_start_s,
        max(time_s)                  as last_lap_end_s
    from {{ ref('fct_lap') }}
    where year >= 2022
    group by 1, 2, 3, 4
),

car as (
    select
        cast(year as integer) as year, cast(round as integer) as round, cast(session as varchar) as session_code,
        count(*)                                        as car_rows,
        count(distinct driver_number)                   as car_drivers,
        cast(min(session_time_s) as double)             as car_start_s,
        cast(max(session_time_s) as double)             as car_end_s
    from {{ source('lake', 'telemetry_car') }}
    group by 1, 2, 3
),

pos as (
    select
        cast(year as integer) as year, cast(round as integer) as round, cast(session as varchar) as session_code,
        count(*)                                        as pos_rows,
        count(distinct driver_number)                   as pos_drivers,
        cast(min(session_time_s) as double)             as pos_start_s,
        cast(max(session_time_s) as double)             as pos_end_s
    from {{ source('lake', 'telemetry_pos') }}
    group by 1, 2, 3
),

joined as (
    select
        l.session_key, l.year, l.round, l.session_code,
        l.session_code in ('Q', 'R', 'S', 'SQ', 'SS')                   as telemetry_expected,
        l.laps_drivers, l.first_lap_start_s, l.last_lap_end_s,
        (c.year is not null)                                             as has_car,
        c.car_rows, c.car_drivers, c.car_start_s, c.car_end_s,
        c.car_rows / (c.car_drivers * (c.car_end_s - c.car_start_s))     as car_rate_hz,
        (p.year is not null)                                             as has_pos,
        p.pos_rows, p.pos_drivers, p.pos_start_s, p.pos_end_s,
        p.pos_rows / (p.pos_drivers * (p.pos_end_s - p.pos_start_s))     as pos_rate_hz,
        c.car_drivers - l.laps_drivers                                   as car_drivers_minus_laps_drivers,
        p.pos_drivers - l.laps_drivers                                   as pos_drivers_minus_laps_drivers
    from laps l
    left join car c using (year, round, session_code)
    left join pos p using (year, round, session_code)
)

select
    *,
    (telemetry_expected and not (has_car and has_pos))                                          as telemetry_missing,
    coalesce(car_end_s < last_lap_end_s - {{ var('telemetry_end_tolerance_s', 60) }}, false)
      or coalesce(pos_end_s < last_lap_end_s - {{ var('telemetry_end_tolerance_s', 60) }}, false) as ends_early,
    coalesce(car_start_s > first_lap_start_s, false)
      or coalesce(pos_start_s > first_lap_start_s, false)                                       as starts_late,
    coalesce(car_rate_hz < {{ var('telemetry_min_rate_hz', 3) }}, false)
      or coalesce(pos_rate_hz < {{ var('telemetry_min_rate_hz', 3) }}, false)                   as thin,
    (telemetry_expected and not (has_car and has_pos))
      or coalesce(car_end_s < last_lap_end_s - {{ var('telemetry_end_tolerance_s', 60) }}, false)
      or coalesce(pos_end_s < last_lap_end_s - {{ var('telemetry_end_tolerance_s', 60) }}, false)
      or coalesce(car_start_s > first_lap_start_s, false)
      or coalesce(pos_start_s > first_lap_start_s, false)
      or coalesce(car_rate_hz < {{ var('telemetry_min_rate_hz', 3) }}, false)
      or coalesce(pos_rate_hz < {{ var('telemetry_min_rate_hz', 3) }}, false)                   as has_issue
from joined
