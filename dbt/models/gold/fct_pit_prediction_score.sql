-- How well fct_pit_now predicted real stops, with two naive guesses beside it so the number means something:
--   "no loss"   the driver keeps the position they had before the stop
--   "global"    the same method with one loss figure for every circuit (predicted_position_global)
-- One row per scope (all stops, or only stops no other driver pitted near it: other_stops_nearby = 0), regime
-- (green, sc, vsc, or all) and margin bucket (or all). hit_rate is the share of stops predicted to the exact place;
-- within_one_rate within one place; mae the mean absolute error in places; bias the mean of predicted minus actual;
-- in_range_rate the share where the actual place fell inside the model's fast-to-slow range. A row with fewer than 30
-- stops is marked is_reliable false. Stops with no margin (no car behind to compare with) form their own bucket, 'no margin'.
with base as (

    select
        c.*,
        abs(c.predicted_position - c.actual_position)         as abs_error,
        abs(c.position_now - c.actual_position)               as abs_error_now,
        abs(c.predicted_position_global - c.actual_position)  as abs_error_global
    from {{ ref('fct_pit_prediction_check') }} c

),

scoped as (

    select 'all' as scope, * from base
    union all
    select 'undisturbed', * from base where other_stops_nearby = 0

),

grouped as (

    select
        scope,
        case when grouping(regime) = 1 then 'all' else regime end                          as regime,
        case when grouping(margin_bucket) = 1 then 'all' else coalesce(margin_bucket, 'no margin') end as margin_bucket,
        count(*)                                                    as stops,
        avg((abs_error = 0)::int)                                   as hit_rate,
        avg((abs_error <= 1)::int)                                  as within_one_rate,
        avg(abs_error)                                              as mae,
        avg(error)                                                  as bias,
        avg(in_range::int)                                          as in_range_rate,
        avg((abs_error_now = 0)::int)                               as no_loss_hit_rate,
        avg(abs_error_now)                                          as no_loss_mae,
        avg((abs_error_global = 0)::int)                            as global_hit_rate,
        avg(abs_error_global)                                       as global_mae
    from scoped
    group by grouping sets ((scope), (scope, regime), (scope, margin_bucket))

)

select
    scope,
    regime,
    margin_bucket,
    cast(stops as integer)                  as stops,
    cast(hit_rate as double)                as hit_rate,
    cast(within_one_rate as double)         as within_one_rate,
    cast(mae as double)                     as mae,
    cast(bias as double)                    as bias,
    cast(in_range_rate as double)           as in_range_rate,
    cast(no_loss_hit_rate as double)        as no_loss_hit_rate,
    cast(no_loss_mae as double)             as no_loss_mae,
    cast(global_hit_rate as double)         as global_hit_rate,
    cast(global_mae as double)              as global_mae,
    cast(stops >= 30 as boolean)            as is_reliable
from grouped
