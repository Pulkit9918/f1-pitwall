-- Silver: the UTC clock time of session second zero, one row per session that has one.
-- LapStartDate (UTC) minus LapStartTime_s (session seconds) is the same for every lap of a session, so the
-- median is used and spread_s (p90 minus p10) is kept to let a test warn if that stops being true.
-- Checked against the first position sample, which is what the Race scrubber page uses: identical in all
-- 269 sessions that have both (experiments/rc_offset.py). Only sessions ingested with lap start dates have a clock.
with raw as (

    select
        cast(year as integer)                                        as year,
        cast(round as integer)                                       as round,
        cast(session as varchar)                                     as session_code,
        epoch(cast(LapStartDate as timestamp)) - LapStartTime_s      as zero_epoch_s
    from {{ source('lake', 'laps') }}
    where LapStartDate is not null and LapStartTime_s is not null

)

select
    {{ session_key('year', 'round', 'session_code') }}                                     as session_key,
    year,
    round,
    session_code,
    median(zero_epoch_s)                                                                    as session_zero_epoch_s,
    make_timestamp(cast(floor(median(zero_epoch_s) * 1000000 + 0.5) as bigint))             as session_zero_utc,
    quantile_cont(zero_epoch_s, 0.9) - quantile_cont(zero_epoch_s, 0.1)                     as spread_s,
    count(*)                                                                                as laps_used
from raw
group by year, round, session_code
