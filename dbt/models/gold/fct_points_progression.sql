-- One row per driver per round of every season: the points scored in that round (race plus sprint), the running
-- total after it, the running win count, and the championship position after it.
--
-- Built from the race results (fct_season_result, Jolpica) and the sprint results (fct_result, FastF1, matched by
-- season, round and driver_id). The last round of a season must equal the official standings (fct_driver_standing);
-- the test points_progression_reconciles checks that from 2018 onward. Older seasons are kept but may not reconcile
-- (dropped scores, shared drives, points awarded for half distances).
--
-- Three data points to know about:
--   * Shared drives (1950s and early 1960s) give a driver several result rows in one round; they are added up, and
--     the constructor is the highest constructor_id of them.
--   * A sprint whose results have positions but no points at all (2024 Brazil and Qatar) gets its points from the
--     finishing position on the 8-7-6-5-4-3-2-1 scale in force since 2022. sprint_points_imputed marks those rounds.
--   * 2021 has three sprint races that are not in the lake (no sprint session for that year), so the 2021 running
--     totals are short by the sprint points. The reconciliation test leaves 2021 out for that reason.
--
-- Every driver who scored or raced in a season has a row for every round of it, with 0 points before they started,
-- so the series can be plotted without gaps. constructor_id is the team the driver raced for in that round; it is null
-- in a round the driver did not enter, and for a sprint-only driver it falls back to their team elsewhere in the season.
-- Position ties are broken by wins, then by driver_id: the official countback on finishing places is not applied.
with race as (
    select
        season, round, driver_id,
        max(constructor_id)                  as constructor_id,
        sum(points)                          as race_points,
        bool_or(coalesce(is_win, false))     as is_win
    from {{ ref('fct_season_result') }}
    group by 1, 2, 3
),

sprint_raw as (
    select
        s.year as season, s.round, r.driver_id, r.position, r.points,
        (s.year >= 2022 and sum(r.points) over (partition by r.session_key) is null) as points_all_missing
    from {{ ref('fct_result') }} r
    join {{ ref('dim_session') }} s on s.session_key = r.session_key
    where s.session_code = 'S'
),

sprint as (
    select
        season, round, driver_id,
        sum(coalesce(
            points,
            case when points_all_missing then
                case position when 1 then 8 when 2 then 7 when 3 then 6 when 4 then 5
                              when 5 then 4 when 6 then 3 when 7 then 2 when 8 then 1 else 0 end
            end
        ))                                              as sprint_points,
        bool_or(points is null and points_all_missing)  as sprint_points_imputed
    from sprint_raw
    group by 1, 2, 3
),

calendar as (
    select distinct season, round from race
),

season_drivers as (
    select season, driver_id from race
    union
    select season, driver_id from sprint
),

grid as (
    select c.season, c.round, d.driver_id
    from calendar c
    join season_drivers d on d.season = c.season
),

scored as (
    select
        g.season, g.round, g.driver_id,
        r.constructor_id,
        coalesce(r.race_points, 0) + coalesce(sp.sprint_points, 0) as points_in_round,
        coalesce(sp.sprint_points, 0)                              as sprint_points,
        coalesce(sp.sprint_points_imputed, false)                  as sprint_points_imputed,
        case when coalesce(r.is_win, false) then 1 else 0 end      as win_in_round
    from grid g
    left join race r on r.season = g.season and r.round = g.round and r.driver_id = g.driver_id
    left join sprint sp on sp.season = g.season and sp.round = g.round and sp.driver_id = g.driver_id
),

running as (
    select
        season, round, driver_id,
        coalesce(constructor_id, max(constructor_id) over (partition by season, driver_id)) as constructor_id,
        points_in_round,
        sprint_points,
        sprint_points_imputed,
        sum(points_in_round) over w as cumulative_points,
        cast(sum(win_in_round) over w as integer) as cumulative_wins
    from scored
    window w as (partition by season, driver_id order by round rows between unbounded preceding and current row)
)

select
    cast(season as varchar) || '-' || lpad(cast(round as varchar), 2, '0') || '-' || driver_id as progression_key,
    season,
    round,
    driver_id,
    constructor_id,
    points_in_round,
    sprint_points,
    sprint_points_imputed,
    cumulative_points,
    cumulative_wins,
    cast(row_number() over (
        partition by season, round
        order by cumulative_points desc, cumulative_wins desc, driver_id
    ) as integer) as championship_position
from running
