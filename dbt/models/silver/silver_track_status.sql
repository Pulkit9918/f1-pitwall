-- Silver: track status changes (clear, yellow, safety car, red, VSC). Present for every session folder in the lake.
-- Code meanings, confirmed against the Message column of the lake: 1 AllClear, 2 Yellow, 4 SCDeployed, 5 Red,
-- 6 VSCDeployed, 7 VSCEnding. A test warns if other codes appear.
with raw as (

    select
        cast(year as integer)       as year,
        cast(round as integer)      as round,
        cast(session as varchar)    as session_code,
        cast(Status as varchar)     as status,
        Message                     as message,
        Time_s                      as time_s
    from {{ source('lake', 'track_status') }}
    where Time_s is not null and Status is not null

)

select
    {{ session_key('year', 'round', 'session_code') }}  as session_key,
    *
from raw
qualify row_number() over (
    partition by year, round, session_code, time_s, status order by time_s
) = 1
