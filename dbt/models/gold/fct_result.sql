-- One row per driver per session classification.
select
    cast(session_key || '-' || driver_code as varchar)  as result_key,
    cast(session_key as varchar)                        as session_key,
    cast(driver_code as varchar)                        as driver_code,
    cast(driver_id as varchar)                          as driver_id,
    cast(team_name as varchar)                          as team_name,
    cast(position as integer)                           as position,
    cast(grid_position as integer)                      as grid_position,
    cast(status as varchar)                             as status,
    cast(points as double)                              as points,
    cast(laps_completed as integer)                     as laps_completed,
    cast(q1_s as double)                                as q1_s,
    cast(q2_s as double)                                as q2_s,
    cast(q3_s as double)                                as q3_s
from {{ ref('silver_results') }}
