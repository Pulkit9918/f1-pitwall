-- The held-out loss was estimated without the race it is scored on. Recomputed independently here: for each scored
-- session the median of the other races' losses at the same circuit (or at all circuits for the global source) must
-- equal loss_held_out_s.
with sessions as (select distinct session_key, circuit_id, loss_source_held_out, loss_held_out_s from {{ ref('fct_pit_prediction_heldout') }}),
l as (select session_key, circuit_id, pit_loss_s from {{ ref('fct_pit_loss') }}),
expected as (
    select s.session_key,
           case when s.loss_source_held_out = 'circuit'
                then (select median(l.pit_loss_s) from l where l.circuit_id = s.circuit_id and l.session_key <> s.session_key)
                else (select median(l.pit_loss_s) from l where l.session_key <> s.session_key) end as expected_s,
           s.loss_held_out_s
    from sessions s
)
select session_key, expected_s, loss_held_out_s from expected where abs(expected_s - loss_held_out_s) > 1e-6
