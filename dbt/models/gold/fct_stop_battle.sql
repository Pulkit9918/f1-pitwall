-- One row per pit stop that was made while a rival was within 3 seconds, and what happened to the pair once both
-- had stopped. Races and sprints.
--
-- For a stop by driver F on lap L, the rival is the car directly ahead of F or directly behind F at the end of
-- lap L-1 with the interval at most 3.0 s (the window is a judgement call, not a physical constant):
--   rival ahead of F  -> F is the attacker and stops first: an undercut attempt
--   rival behind F    -> the rival is the attacker and stays out longer: an overcut attempt
-- The rival's response is its next stop at a lap after L and within 12 laps. The outcome is read on the rival's
-- out lap (lap M+1, M being the response stop): did the attacker finish that lap ahead of the defender?
-- Pairs where the rival stopped on the same lap, or on L-1, are skipped; so are pairs with no response stop
-- inside the window or no lap data for both cars at the settle lap.
--
-- This detects an order change between two cars around their stops. It does not prove the stop caused it:
-- traffic, other stops, tyre offsets, safety cars and plain pace all move the same two cars. Rows with
-- either stop not under green flag carry is_neutralised so they can be left out.
with stops as (
    select session_key, driver_code, cast(in_lap as integer) as in_lap,
           bool_and(is_green_stop) as is_green_stop, any_value(compound_after) as compound_after
    from {{ ref('fct_pit_stop') }}
    where session_code in ('R', 'S') and in_lap is not null
    group by session_key, driver_code, in_lap
),

near as (
    select
        s.session_key, s.driver_code as first_code, s.in_lap as first_lap, s.is_green_stop as first_green,
        s.compound_after as first_compound_after,
        g.car_ahead_code as rival_code, g.interval_s as gap_before_s, 'undercut' as kind,
        s.driver_code as attacker_code, g.car_ahead_code as defender_code
    from stops s
    join {{ ref('fct_lap_gap') }} g
      on g.session_key = s.session_key and g.driver_code = s.driver_code and g.lap_number = s.in_lap - 1
    where g.interval_s <= 3.0 and g.car_ahead_code is not null
    union all
    select
        s.session_key, s.driver_code, s.in_lap, s.is_green_stop, s.compound_after,
        g.car_behind_code, g.gap_behind_s, 'overcut',
        g.car_behind_code, s.driver_code
    from stops s
    join {{ ref('fct_lap_gap') }} g
      on g.session_key = s.session_key and g.driver_code = s.driver_code and g.lap_number = s.in_lap - 1
    where g.gap_behind_s <= 3.0 and g.car_behind_code is not null
),

answered as (
    select
        n.*,
        r.in_lap as second_lap, r.is_green_stop as second_green, r.compound_after as second_compound_after
    from near n
    join stops r
      on r.session_key = n.session_key and r.driver_code = n.rival_code
     and r.in_lap = (select min(x.in_lap) from stops x
                     where x.session_key = n.session_key and x.driver_code = n.rival_code and x.in_lap > n.first_lap)
     and r.in_lap - n.first_lap <= 12
    where not exists (select 1 from stops x
                      where x.session_key = n.session_key and x.driver_code = n.rival_code
                        and x.in_lap in (n.first_lap - 1, n.first_lap))
),

settled as (
    select
        a.*,
        att.position as attacker_position_after, att.time_s as attacker_time_after_s,
        dfd.position as defender_position_after, dfd.time_s as defender_time_after_s,
        att.year, att.round, att.session_code
    from answered a
    join {{ ref('fct_lap_gap') }} att
      on att.session_key = a.session_key and att.driver_code = a.attacker_code and att.lap_number = a.second_lap + 1
    join {{ ref('fct_lap_gap') }} dfd
      on dfd.session_key = a.session_key and dfd.driver_code = a.defender_code and dfd.lap_number = a.second_lap + 1
)

select
    session_key || '-' || first_code || '-L' || cast(first_lap as varchar) || '-' || rival_code   as battle_key,
    session_key,
    cast(year as integer)                                            as year,
    cast(round as integer)                                           as round,
    session_code,
    kind,
    attacker_code,
    defender_code,
    first_code                                                       as first_stopper_code,
    rival_code                                                       as second_stopper_code,
    cast(first_lap as integer)                                       as first_stop_lap,
    cast(second_lap as integer)                                      as second_stop_lap,
    cast(second_lap - first_lap as integer)                          as laps_between_stops,
    cast(gap_before_s as double)                                     as gap_before_s,
    first_compound_after,
    second_compound_after,
    attacker_position_after < defender_position_after                as attacker_ahead_after,
    cast(defender_time_after_s - attacker_time_after_s as double)    as margin_after_s,
    coalesce(not (first_green and second_green), true)               as is_neutralised
from settled
