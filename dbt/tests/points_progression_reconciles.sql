-- Fails for every driver whose running points total, at the round the official standings were taken, differs from the
-- official total. 2018 onward: earlier seasons used dropped scores and shared drives, so they are not expected to match.
--
-- Two exceptions, both explained by the data and not by the model:
--   * 2021 is left out: its three sprint races are not in the lake, so 2021 totals are short by their points.
--   * A driver with a sprint whose points were worked out from the finishing position (sprint_points_imputed) may be up
--     to 2 points out, because a penalty after the finish can move a place. 2024 Brazil is off by one point this way.
with imputed as (
    select season, driver_id, bool_or(sprint_points_imputed) as has_imputed_sprint
    from {{ ref('fct_points_progression') }}
    group by 1, 2
)

select
    o.season, o.round, o.driver_id,
    o.points as official_points,
    p.cumulative_points as summed_points,
    coalesce(i.has_imputed_sprint, false) as has_imputed_sprint
from {{ ref('fct_driver_standing') }} o
left join {{ ref('fct_points_progression') }} p
  on p.season = o.season and p.round = o.round and p.driver_id = o.driver_id
left join imputed i
  on i.season = o.season and i.driver_id = o.driver_id
where o.season >= 2018
  and o.season <> 2021
  and abs(o.points - coalesce(p.cumulative_points, -1))
      > case when coalesce(i.has_imputed_sprint, false) then 2.001 else 0.001 end
