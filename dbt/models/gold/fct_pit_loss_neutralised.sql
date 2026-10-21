-- One row per pit stop made entirely under a safety car or a virtual safety car, whose time loss could be
-- measured, races and sprints from 2018.
--
-- Same arithmetic as fct_pit_loss: loss = (in-lap time - field) + (out-lap time - field), the extra time the stop
-- costs over two laps against the median of the cars that did not pit on that lap. Differences from the green
-- version, all deliberate:
--   * both laps must be on a single track status: exactly '4' (safety car) or exactly '6' (virtual safety car);
--     laps with mixed codes (a restart, a yellow, the SC coming in) are not measured
--   * the driver's own pace offset is taken as zero: under a neutralisation the field is bunched and set by the
--     car in front, so there are no clean laps to measure an offset from
-- That makes these figures rougher than the green-flag ones. They are an estimate of what a stop costs under
-- neutralisation, not a measurement of any one driver.
with laps as (
    select
        l.session_key, l.year, l.round, l.session_code, l.driver_code, l.lap_number, l.lap_time_s,
        l.pit_in_time_s, l.pit_out_time_s, l.track_status,
        (l.pit_in_time_s is null and l.pit_out_time_s is null and l.lap_time_s is not null) as is_unpitted_lap
    from {{ ref('fct_lap') }} l
    where l.session_code in ('R', 'S')
),

field as (
    select session_key, lap_number, median(lap_time_s) as field_s
    from laps
    where is_unpitted_lap
    group by session_key, lap_number
),

stop_laps as (
    select
        a.session_key, a.year, a.round, a.session_code, a.driver_code, a.lap_number as in_lap,
        case when a.track_status = '4' then 'sc' else 'vsc' end as regime,
        (a.lap_time_s - fa.field_s) + (b.lap_time_s - fb.field_s) as loss_s
    from laps a
    join laps b
      on b.session_key = a.session_key and b.driver_code = a.driver_code and b.lap_number = a.lap_number + 1
    join field fa on fa.session_key = a.session_key and fa.lap_number = a.lap_number
    join field fb on fb.session_key = b.session_key and fb.lap_number = b.lap_number
    where a.pit_in_time_s is not null
      and b.pit_out_time_s is not null
      and a.lap_time_s is not null and b.lap_time_s is not null
      and a.track_status = b.track_status
      and a.track_status in ('4', '6')
)

select
    s.session_key || '-' || s.driver_code || '-L' || cast(s.in_lap as varchar)  as pit_loss_key,
    s.session_key,
    cast(s.year as integer)                                                     as year,
    cast(s.round as integer)                                                    as round,
    s.session_code,
    s.driver_code,
    cast(s.in_lap as integer)                                                   as in_lap,
    s.regime,
    c.circuit_id,
    cast(s.loss_s as double)                                                    as pit_loss_s
from stop_laps s
left join {{ ref('dim_session_circuit') }} c on c.session_key = s.session_key
