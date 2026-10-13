-- Silver: typed race control messages with a stable per-session sequence number.
with raw as (

    select
        cast(year as integer)               as year,
        cast(round as integer)              as round,
        cast(session as varchar)            as session_code,
        event,
        Time                                as message_time,
        Category                            as category,
        Flag                                as flag,
        Scope                               as scope,
        cast(Sector as integer)             as sector,
        RacingNumber                        as racing_number,
        cast(Lap as integer)                as lap_number,
        Message                             as message,
        upper(Message)                      as message_upper
    from {{ source('lake', 'race_control') }}
    where Message is not null

)

select
    {{ session_key('year', 'round', 'session_code') }}  as session_key,
    {{ session_key('year', 'round', 'session_code') }} || '-'
        || cast(row_number() over (
            partition by year, round, session_code
            order by message_time, message
        ) as varchar)                                    as event_key,
    *
from raw
