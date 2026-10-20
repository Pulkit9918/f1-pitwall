-- One row per green-flag pit stop whose time loss could be measured, 2018 onward, races and sprints.
--
-- Loss = (in-lap time - field - offset) + (out-lap time - field - offset), the extra time the stop costs
-- over two laps at the field's pace, so it does not depend on the driver:
--   field  = median lap time of all cars on that lap, over laps without a pit-in or pit-out time
--   offset = the driver's median gap to the field over the 4 laps before and the 4 laps after the stop
--            (laps without a pit time, on track status 1 exactly; at least 3 needed)
-- Both the in-lap and the out-lap must be on track status 1 (all clear). Safety car, VSC and yellow-flag
-- stops are not measured: the method does not work for them.
-- Same method as experiments/pitloss_probe.py and experiments/pitloss_circuit.py (reconciled stop by stop).
with laps as (
    select
        l.session_key, l.year, l.round, l.session_code, l.driver_code, l.lap_number, l.lap_time_s,
        l.pit_in_time_s, l.pit_out_time_s,
        (l.pit_in_time_s is null and l.pit_out_time_s is null and l.lap_time_s is not null) as is_unpitted_lap,
        (l.track_status = '1')                                                              as is_status_clear
    from {{ ref('fct_lap') }} l
    where l.session_code in ('R', 'S')
),

field as (
    select session_key, lap_number, median(lap_time_s) as field_s
    from laps
    where is_unpitted_lap
    group by session_key, lap_number
),

laps_f as (
    select l.*, f.field_s
    from laps l
    left join field f using (session_key, lap_number)
),

stop_laps as (
    select
        a.session_key, a.year, a.round, a.session_code, a.driver_code, a.lap_number as in_lap,
        a.lap_time_s as in_lap_time_s, b.lap_time_s as out_lap_time_s,
        a.field_s as in_field_s, b.field_s as out_field_s
    from laps_f a
    join laps_f b
      on b.session_key = a.session_key and b.driver_code = a.driver_code and b.lap_number = a.lap_number + 1
    where a.pit_in_time_s is not null
      and b.pit_out_time_s is not null
      and a.is_status_clear and b.is_status_clear
      and a.lap_time_s is not null and b.lap_time_s is not null
      and a.field_s is not null and b.field_s is not null
),

offsets as (
    select s.session_key, s.driver_code, s.in_lap,
           median(c.lap_time_s - c.field_s) as driver_offset_s,
           count(*)                         as offset_laps
    from stop_laps s
    join laps_f c
      on c.session_key = s.session_key and c.driver_code = s.driver_code
     and (c.lap_number between s.in_lap - 4 and s.in_lap - 1
          or c.lap_number between s.in_lap + 2 and s.in_lap + 5)
    where c.is_unpitted_lap and c.is_status_clear and c.field_s is not null
    group by s.session_key, s.driver_code, s.in_lap
    having count(*) >= 3
)

select
    s.session_key || '-' || s.driver_code || '-L' || cast(s.in_lap as varchar)  as pit_loss_key,
    s.session_key,
    s.year,
    s.round,
    s.session_code,
    s.driver_code,
    s.in_lap,
    c.circuit_id,
    c.circuit_name,
    c.circuit_layout_key,
    (s.in_lap_time_s - s.in_field_s - o.driver_offset_s)
        + (s.out_lap_time_s - s.out_field_s - o.driver_offset_s)                as pit_loss_s,
    o.driver_offset_s,
    o.offset_laps
from stop_laps s
join offsets o using (session_key, driver_code, in_lap)
join {{ ref('dim_session_circuit') }} c using (session_key)
