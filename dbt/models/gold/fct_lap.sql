-- One row per driver lap, with the driver's id and a "clean lap" flag for pace statistics.
-- A clean lap: green track, accurate timing, not deleted, not an in-lap or out-lap, has a time.
select
    l.session_key,
    l.lap_key,
    l.year,
    l.round,
    l.session_code,
    l.driver_code,
    r.driver_id,
    l.team,
    l.lap_number,
    l.stint,
    l.compound,
    l.tyre_life,
    l.position,
    l.track_status,
    l.is_green,
    l.deleted,
    l.is_accurate,
    l.lap_time_s,
    l.lap_start_time_s,
    l.time_s,
    l.pit_in_time_s,
    l.pit_out_time_s,
    l.sector1_s,
    l.sector2_s,
    l.sector3_s,
    (l.is_green and l.is_accurate and not l.deleted
        and l.pit_in_time_s is null and l.pit_out_time_s is null
        and l.lap_time_s is not null)                           as is_clean_lap
from {{ ref('silver_laps') }} l
left join {{ ref('silver_results') }} r
    on  r.session_key = l.session_key
    and r.driver_code = l.driver_code
