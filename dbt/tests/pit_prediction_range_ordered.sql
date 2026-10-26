{{ config(severity='warn') }}
-- A quick stop should never be predicted a worse place than a slow one: fast <= predicted <= slow. A row that breaks
-- this means the circuit's loss percentiles or the regime ratios are out of order.
select pit_stop_key, predicted_position_fast, predicted_position, predicted_position_slow
from {{ ref('fct_pit_prediction_check') }}
where predicted_position_fast > predicted_position or predicted_position > predicted_position_slow
