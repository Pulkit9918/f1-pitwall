-- fct_pit_prediction_score adds up: the all/all row counts every checked stop, the regime rows and the margin rows
-- each add up to the same total, undisturbed stops are a subset, and every rate is a share.
with s as (select * from {{ ref('fct_pit_prediction_score') }}),
total as (select count(*) as n from {{ ref('fct_pit_prediction_check') }}),
undisturbed as (select count(*) as n from {{ ref('fct_pit_prediction_check') }} where other_stops_nearby = 0)
select 'all total' as problem from s, total where s.scope = 'all' and s.regime = 'all' and s.margin_bucket = 'all' and s.stops <> total.n
union all
select 'regime sum' from total where (select coalesce(sum(stops), 0) from s where scope = 'all' and regime <> 'all') <> total.n
union all
select 'margin sum' from total where (select coalesce(sum(stops), 0) from s where scope = 'all' and margin_bucket <> 'all') <> total.n
union all
select 'undisturbed total' from undisturbed where (select coalesce(sum(stops), 0) from s where scope = 'undisturbed' and regime = 'all' and margin_bucket = 'all') <> undisturbed.n
union all
select 'rate' from s
where hit_rate not between 0 and 1 or within_one_rate not between 0 and 1 or in_range_rate not between 0 and 1
   or no_loss_hit_rate not between 0 and 1 or global_hit_rate not between 0 and 1
   or hit_rate > within_one_rate or mae < 0
