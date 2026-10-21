-- How much a stop under a safety car or virtual safety car costs compared with a green-flag stop, as a ratio of
-- medians across all circuits: neutralised median loss divided by the green median loss from fct_pit_loss.
-- The ratio is applied to a circuit's own green-flag loss in fct_pit_now. One row for green (ratio 1), one for
-- each neutralisation. is_reliable needs at least 30 measured stops.
with green as (
    select
        median(pit_loss_s)                       as median_s,
        quantile_cont(pit_loss_s, 0.25)          as p25_s,
        quantile_cont(pit_loss_s, 0.75)          as p75_s,
        count(*)                                 as stops
    from {{ ref('fct_pit_loss') }}
),

neutral as (
    select
        regime,
        count(*)                                 as stops,
        median(pit_loss_s)                       as median_s,
        quantile_cont(pit_loss_s, 0.25)          as p25_s,
        quantile_cont(pit_loss_s, 0.75)          as p75_s
    from {{ ref('fct_pit_loss_neutralised') }}
    group by regime
),

all_regimes as (
    select 'green' as regime, stops, median_s, p25_s, p75_s from green
    union all
    select regime, stops, median_s, p25_s, p75_s from neutral
)

select
    r.regime,
    cast(r.stops as integer)                                  as stops,
    cast(r.median_s as double)                                as median_loss_s,
    cast(r.p25_s as double)                                   as p25_loss_s,
    cast(r.p75_s as double)                                   as p75_loss_s,
    cast(r.median_s / g.median_s as double)                   as ratio_to_green,
    cast(r.p25_s / g.median_s as double)                      as p25_ratio_to_green,
    cast(r.p75_s / g.median_s as double)                      as p75_ratio_to_green,
    r.stops >= 30                                             as is_reliable
from all_regimes r
cross join green g
