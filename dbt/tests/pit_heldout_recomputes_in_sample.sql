-- The held-out model's own recomputation reproduces what fct_pit_now stored, so the held-out numbers differ from the
-- in-sample ones only because the loss left the scored race out. Both the loss and the predicted place must match.
select pit_stop_key, 'loss' as problem
from {{ ref('fct_pit_prediction_heldout') }}
where abs(loss_recomputed_s - loss_in_sample_s) > 1e-6
union all
select pit_stop_key, 'prediction'
from {{ ref('fct_pit_prediction_heldout') }}
where predicted_recomputed <> predicted_in_sample
