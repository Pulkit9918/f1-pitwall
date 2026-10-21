-- fct_pit_now against what happened: one row for every real stop (in-lap L+1) that has a prediction made at the
-- end of lap L. actual_position is the driver's position at the end of the out-lap (L+2).
--
-- Other cars stopping at the same time move the field, which the prediction does not model, so is_quiet marks
-- stops where no other driver pitted on laps L+1 or L+2, and regime_matches marks stops whose own lap had the
-- same track regime the prediction assumed (a stop that happens under a safety car that was not yet out when the
-- prediction was made does not test the predictor); judge it on stops where both hold. The circuit loss
-- includes the stops being tested (nothing is held out), so the error is a little flattering.
with actual as (
    select session_key, driver_code, cast(in_lap as integer) as in_lap
    from {{ ref('fct_pit_stop') }}
    where session_code in ('R', 'S') and in_lap is not null
    group by session_key, driver_code, in_lap
),

joined as (
    select
        p.pit_now_key, p.session_key, p.year, p.round, p.session_code, p.driver_code, p.lap_number,
        p.regime, p.loss_source, p.position_now, p.predicted_position, p.predicted_position_fast,
        p.predicted_position_slow, p.predicted_position_global, p.margin_s,
        o.position as actual_position,
        case when s.track_status like '%5%' then 'red'
             when s.track_status like '%4%' then 'sc'
             when s.track_status like '%6%' or s.track_status like '%7%' then 'vsc'
             else 'green' end as stop_regime
    from {{ ref('fct_pit_now') }} p
    join actual a
      on a.session_key = p.session_key and a.driver_code = p.driver_code and a.in_lap = p.lap_number + 1
    join {{ ref('fct_lap_gap') }} o
      on o.session_key = p.session_key and o.driver_code = p.driver_code and o.lap_number = p.lap_number + 2
    join {{ ref('fct_lap_gap') }} s
      on s.session_key = p.session_key and s.driver_code = p.driver_code and s.lap_number = p.lap_number + 1
    where p.predicted_position is not null
)

select
    j.pit_now_key,
    j.session_key,
    j.year,
    j.round,
    j.session_code,
    j.driver_code,
    j.lap_number,
    j.regime,
    j.stop_regime,
    j.regime = j.stop_regime                                             as regime_matches,
    j.loss_source,
    j.position_now,
    j.predicted_position,
    j.predicted_position_fast,
    j.predicted_position_slow,
    j.predicted_position_global,
    cast(j.actual_position as integer)                                  as actual_position,
    cast(j.actual_position - j.predicted_position as integer)           as error_places,
    cast(abs(j.actual_position - j.predicted_position) as integer)      as abs_error_places,
    cast(abs(j.actual_position - j.predicted_position_global) as integer) as abs_error_global_places,
    j.actual_position between j.predicted_position_fast and j.predicted_position_slow as within_range,
    not exists (
        select 1 from actual x
        where x.session_key = j.session_key and x.driver_code <> j.driver_code
          and x.in_lap in (j.lap_number + 1, j.lap_number + 2)
    )                                                                   as is_quiet
from joined j
