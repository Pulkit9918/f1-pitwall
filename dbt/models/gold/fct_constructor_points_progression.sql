-- One row per constructor per round of every season: the points its drivers scored in that round (race plus sprint),
-- the running total after it, and the constructors' championship position after it.
--
-- Built from fct_points_progression by summing each driver's points under the team they raced for in that round.
-- The last round of a season must equal the official standings (fct_constructor_standing); the test
-- constructor_points_progression_reconciles checks that from 2018 onward. Seasons with points deductions or
-- disqualified teams will not reconcile. Ties are broken by constructor_id.
with by_round as (
    select season, round, constructor_id, sum(points_in_round) as points_in_round
    from {{ ref('fct_points_progression') }}
    where constructor_id is not null
    group by 1, 2, 3
),

calendar as (
    select distinct season, round from by_round
),

season_constructors as (
    select distinct season, constructor_id from by_round
),

grid as (
    select c.season, c.round, k.constructor_id
    from calendar c
    join season_constructors k on k.season = c.season
),

running as (
    select
        g.season, g.round, g.constructor_id,
        coalesce(b.points_in_round, 0) as points_in_round,
        sum(coalesce(b.points_in_round, 0)) over (
            partition by g.season, g.constructor_id order by g.round
            rows between unbounded preceding and current row
        ) as cumulative_points
    from grid g
    left join by_round b on b.season = g.season and b.round = g.round and b.constructor_id = g.constructor_id
)

select
    cast(season as varchar) || '-' || lpad(cast(round as varchar), 2, '0') || '-' || constructor_id as progression_key,
    season,
    round,
    constructor_id,
    points_in_round,
    cumulative_points,
    cast(row_number() over (partition by season, round order by cumulative_points desc, constructor_id) as integer) as championship_position
from running
