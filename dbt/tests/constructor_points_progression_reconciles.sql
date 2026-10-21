-- Fails for every constructor whose running points total, at the round the official standings were taken, differs from
-- the official total. 2018 onward.
--
-- Exceptions, all explained by the data and not by the model:
--   * 2021 is left out: its three sprint races are not in the lake, so 2021 totals are short by their points.
--   * Racing Point 2020: the official standings carry a 15-point deduction that the race results do not.
--   * A constructor with a driver whose sprint points were worked out from the finishing position
--     (sprint_points_imputed) may be up to 2 points out, because a penalty after the finish can move a place.
with imputed as (
    select season, constructor_id, bool_or(sprint_points_imputed) as has_imputed_sprint
    from {{ ref('fct_points_progression') }}
    where constructor_id is not null
    group by 1, 2
)

select
    o.season, o.round, o.constructor_id,
    o.points as official_points,
    p.cumulative_points as summed_points,
    coalesce(i.has_imputed_sprint, false) as has_imputed_sprint
from {{ ref('fct_constructor_standing') }} o
left join {{ ref('fct_constructor_points_progression') }} p
  on p.season = o.season and p.round = o.round and p.constructor_id = o.constructor_id
left join imputed i
  on i.season = o.season and i.constructor_id = o.constructor_id
where o.season >= 2018
  and o.season <> 2021
  and not (o.season = 2020 and o.constructor_id = 'racing_point')
  and abs(o.points - coalesce(p.cumulative_points, -1))
      > case when coalesce(i.has_imputed_sprint, false) then 2.001 else 0.001 end
