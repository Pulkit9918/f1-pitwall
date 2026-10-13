-- Silver: typed, deduplicated laps. One row per (session, driver, lap number).
-- Raw rows without a driver or lap number are dropped; duplicates keep the row with the latest end time.
with raw as (

    select
        cast(year as integer)                                   as year,
        cast(round as integer)                                  as round,
        cast(session as varchar)                                as session_code,
        event,
        cast(Driver as varchar)                                 as driver_code,
        cast(DriverNumber as varchar)                           as driver_number,
        Team                                                    as team,
        cast(LapNumber as integer)                              as lap_number,
        cast(Stint as integer)                                  as stint,
        Compound                                                as compound,
        TyreLife                                                as tyre_life,
        FreshTyre                                               as fresh_tyre,
        cast(Position as integer)                               as position,
        cast(TrackStatus as varchar)                            as track_status,
        coalesce(TrackStatus = '1', false)                      as is_green,
        coalesce(Deleted, false)                                as deleted,
        DeletedReason                                           as deleted_reason,
        coalesce(IsAccurate, false)                             as is_accurate,
        coalesce(FastF1Generated, false)                        as fastf1_generated,
        coalesce(IsPersonalBest, false)                         as is_personal_best,
        LapTime_s                                               as lap_time_s,
        LapStartTime_s                                          as lap_start_time_s,
        Time_s                                                  as time_s,
        PitInTime_s                                             as pit_in_time_s,
        PitOutTime_s                                            as pit_out_time_s,
        Sector1Time_s                                           as sector1_s,
        Sector2Time_s                                           as sector2_s,
        Sector3Time_s                                           as sector3_s,
        SpeedI1                                                 as speed_i1,
        SpeedI2                                                 as speed_i2,
        SpeedFL                                                 as speed_fl,
        SpeedST                                                 as speed_st
    from {{ source('lake', 'laps') }}
    where LapNumber is not null
      and Driver is not null

)

select
    {{ session_key('year', 'round', 'session_code') }}                        as session_key,
    {{ session_key('year', 'round', 'session_code') }} || '-' || driver_code
        || '-' || cast(lap_number as varchar)                                as lap_key,
    *
from raw
qualify row_number() over (
    partition by year, round, session_code, driver_code, lap_number
    order by time_s desc nulls last
) = 1
