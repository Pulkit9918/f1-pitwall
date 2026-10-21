-- One row per driver per lap of a race or sprint: where the driver would rejoin if they pitted at the end of
-- that lap (so the stop happens on the next lap), and how sure that is.
--
-- Method. Take every car's lap-end time at the lap just finished. A stop costs the driver pit_loss_s seconds
-- against the field. The driver rejoins behind every car that is currently within pit_loss_s behind them, and
-- ahead of the rest:   predicted_position = 1 + number of other cars with lap-end time < own time + pit_loss_s.
-- Cars currently ahead stay ahead. Cars further back than the loss stay behind. A car a lap down is compared by
-- lap-number time, so it is behind unless the loss is longer than a lap.
--
-- The loss comes from the regime of the lap just finished (track status): green or yellow uses the circuit's
-- median green-flag loss (or the all-circuit median where the circuit figure is not reliable); a safety car or
-- VSC uses that figure times the measured ratio in fct_pit_loss_ratio; a red flag has no prediction because the
-- pit lane is closed and the field queues. predicted_position_fast and _slow use the middle half of the
-- circuit's observed losses (p25 and p75), so the three together are a range, not a probability.
--
-- What it assumes: every other car keeps its pace and does not stop in the meantime, the driver's out-lap is as
-- fast as the field's, and the loss does not depend on the driver. margin_s is how many seconds of loss
-- separate the prediction from the next place changing, so a small margin means the answer is on the edge.
with laps as (
    select session_key, lap_key, year, round, session_code, driver_code, lap_number, position, time_s, track_status
    from {{ ref('fct_lap_gap') }}
),

regime as (
    select
        *,
        case when track_status like '%5%' then 'red'
             when track_status like '%4%' then 'sc'
             when track_status like '%6%' or track_status like '%7%' then 'vsc'
             else 'green' end as regime
    from laps
),

global_green as (
    select median_loss_s as mid_s, p25_loss_s as lo_s, p75_loss_s as hi_s from {{ ref('fct_pit_loss_ratio') }} where regime = 'green'
),

ratios as (
    select regime, ratio_to_green as r_mid, p25_ratio_to_green as r_lo, p75_ratio_to_green as r_hi
    from {{ ref('fct_pit_loss_ratio') }}
),

circuit as (
    select sc.session_key, cl.is_reliable as circuit_reliable,
           cl.median_pit_loss_s as c_mid, cl.p25_pit_loss_s as c_lo, cl.p75_pit_loss_s as c_hi
    from {{ ref('dim_session_circuit') }} sc
    left join {{ ref('fct_circuit_pit_loss') }} cl using (circuit_id)
),

with_loss as (
    select
        x.*,
        coalesce(c.circuit_reliable, false)                                    as use_circuit,
        case when coalesce(c.circuit_reliable, false) then c.c_mid else g.mid_s end as green_mid,
        case when coalesce(c.circuit_reliable, false) then c.c_lo  else g.lo_s  end as green_lo,
        case when coalesce(c.circuit_reliable, false) then c.c_hi  else g.hi_s  end as green_hi,
        g.mid_s as global_mid
    from regime x
    left join circuit c using (session_key)
    cross join global_green g
),

scaled as (
    select
        w.*,
        case w.regime when 'green' then w.green_mid
                      when 'red' then null
                      else w.green_mid * r.r_mid end as loss_mid,
        case w.regime when 'green' then w.green_lo
                      when 'red' then null
                      else w.green_lo * r.r_lo end as loss_lo,
        case w.regime when 'green' then w.green_hi
                      when 'red' then null
                      else w.green_hi * r.r_hi end as loss_hi
    from with_loss w
    left join ratios r on r.regime = w.regime
),

counted as (
    select
        s.*,
        count(o.driver_code) filter (where o.time_s < s.time_s + s.loss_mid)    as ahead_mid,
        count(o.driver_code) filter (where o.time_s < s.time_s + s.loss_lo)     as ahead_lo,
        count(o.driver_code) filter (where o.time_s < s.time_s + s.loss_hi)     as ahead_hi,
        count(o.driver_code) filter (where o.time_s < s.time_s + s.global_mid)  as ahead_global,
        min(abs(o.time_s - (s.time_s + s.loss_mid))) filter (where o.time_s >= s.time_s) as margin
    from scaled s
    left join laps o
      on o.session_key = s.session_key and o.lap_number = s.lap_number and o.driver_code <> s.driver_code
    group by all
)

select
    lap_key                                                  as pit_now_key,
    session_key,
    cast(year as integer)                                    as year,
    cast(round as integer)                                   as round,
    session_code,
    driver_code,
    cast(lap_number as integer)                              as lap_number,
    cast(position as integer)                                as position_now,
    regime,
    case when regime = 'red' then null
         when use_circuit then 'circuit' else 'global' end   as loss_source,
    cast(loss_mid as double)                                 as pit_loss_s,
    cast(case when loss_mid is null then null else 1 + ahead_mid end as integer)                           as predicted_position,
    cast(case when loss_mid is null then null else 1 + ahead_lo end as integer)                            as predicted_position_fast,
    cast(case when loss_mid is null then null else 1 + ahead_hi end as integer)                            as predicted_position_slow,
    cast(case when loss_mid is null then null else 1 + ahead_global end as integer)                        as predicted_position_global,
    cast(margin as double)                                   as margin_s
from counted
