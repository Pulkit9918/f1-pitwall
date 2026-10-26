-- fct_pit_prediction_check agrees with its sources and with its own definitions: the prediction is the one made on the
-- lap before the stop, the outcome is the position at the end of the out-lap, and the derived columns follow from them.
select c.pit_stop_key, 'error' as problem
from {{ ref('fct_pit_prediction_check') }} c
where c.error <> c.predicted_position - c.actual_position
   or c.in_range <> (c.actual_position between c.predicted_position_fast and c.predicted_position_slow)
union all
select c.pit_stop_key, 'prediction'
from {{ ref('fct_pit_prediction_check') }} c
join {{ ref('fct_pit_stop') }} s on s.pit_stop_key = c.pit_stop_key
join {{ ref('fct_pit_now') }} p on p.session_key = s.session_key and p.driver_code = s.driver_code and p.lap_number = s.in_lap - 1
where c.predicted_position is distinct from p.predicted_position
   or c.margin_s is distinct from p.margin_s
union all
select c.pit_stop_key, 'outcome'
from {{ ref('fct_pit_prediction_check') }} c
join {{ ref('fct_pit_stop') }} s on s.pit_stop_key = c.pit_stop_key
join {{ ref('fct_lap_gap') }} a on a.session_key = s.session_key and a.driver_code = s.driver_code and a.lap_number = s.in_lap + 1
where c.actual_position is distinct from a.position
