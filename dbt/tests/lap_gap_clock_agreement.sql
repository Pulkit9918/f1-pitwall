-- Recorded order and the session clock should rarely disagree. Fails if more than 2% of laps in any season do.
-- A season needs at least 500 laps to be judged: a percentage over a handful of laps (the synthetic CI lake) means nothing.
select year, count(*) as laps, sum(order_disagrees_with_clock::int) as disagreeing
from {{ ref('fct_lap_gap') }}
group by year
having count(*) >= 500
   and sum(order_disagrees_with_clock::int) > 0.02 * count(*)
