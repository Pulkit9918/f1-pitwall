-- Silver: track status changes (clear, yellow, safety car, red, VSC). Only sessions ingested from 2024 on.
-- Code meanings are my reading of the FastF1 documentation: 1 clear, 2 yellow, 4 safety car, 5 red,
-- 6 VSC deployed, 7 VSC ending. A test warns if other codes appear.
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
