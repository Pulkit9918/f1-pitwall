-- In-sample against held-out accuracy of the pit-now prediction on the same green-flag stops, for all stops and for
-- undisturbed stops (no other driver pitting from the lap before the stop to the out-lap). hit_rate is the share
-- predicted to the exact place, mae the mean absolute error in places. loss_shift_s is the mean of the held-out loss
-- minus the in-sample loss, in seconds, and held_out_circuit_share the share of stops whose held-out loss came from the
-- circuit's other races rather than the global figure.
with scoped as (

    select 'all' as scope, * from {{ ref('fct_pit_prediction_heldout') }}
    union all
    select 'undisturbed', * from {{ ref('fct_pit_prediction_heldout') }} where other_stops_nearby = 0

)

select
    scope,
    cast(count(*) as integer)                                                                 as stops,
    cast(avg((predicted_in_sample = actual_position)::int) as double)                         as in_sample_hit_rate,
    cast(avg((predicted_held_out = actual_position)::int) as double)                          as held_out_hit_rate,
    cast(avg(abs(predicted_in_sample - actual_position)) as double)                           as in_sample_mae,
    cast(avg(abs(predicted_held_out - actual_position)) as double)                            as held_out_mae,
    cast(avg(loss_held_out_s - loss_in_sample_s) as double)                                   as loss_shift_s,
    cast(avg((loss_source_held_out = 'circuit')::int) as double)                              as held_out_circuit_share
from scoped
group by scope
