select
    cast(session_key as varchar)        as session_key,
    cast(year as integer)               as year,
    cast(round as integer)              as round,
    cast(session_code as varchar)       as session_code,
    cast(case session_code
        when 'R'   then 'Race'
        when 'Q'   then 'Qualifying'
        when 'S'   then 'Sprint'
        when 'SQ'  then 'Sprint Qualifying'
        when 'SS'  then 'Sprint Shootout'
        when 'FP1' then 'Practice 1'
        when 'FP2' then 'Practice 2'
        when 'FP3' then 'Practice 3'
        else session_code
    end as varchar)                     as session_name,
    cast(event as varchar)              as event,
    cast(has_laps as boolean)           as has_laps,
    cast(has_results as boolean)        as has_results,
    cast(has_race_control as boolean)   as has_race_control
from {{ ref('silver_sessions') }}
