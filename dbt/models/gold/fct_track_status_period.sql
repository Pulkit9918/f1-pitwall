-- Track status as time periods per session: each row runs from one status change to the next.
-- end_s is null for the last change of a session. Times are session seconds, like the lap tables.
select
    session_key || '-' || cast(row_number() over (
        partition by session_key order by time_s, status) as varchar)           as period_key,
    session_key,
    year,
    round,
    session_code,
    status,
    case status
        when '1' then 'CLEAR'
        when '2' then 'YELLOW'
        when '4' then 'SAFETY_CAR'
        when '5' then 'RED'
        when '6' then 'VSC'
        when '7' then 'VSC_ENDING'
        else 'OTHER'
    end                                                                           as meaning,
    message,
    time_s                                                                        as start_s,
    lead(time_s) over (partition by session_key order by time_s, status)         as end_s
from {{ ref('silver_track_status') }}
