-- Each battle must be what it says: the attacker was behind the defender the lap before the first stop,
-- the sign of the margin matches the outcome, and the stops are in order.
select b.battle_key
from {{ ref('fct_stop_battle') }} b
left join {{ ref('fct_lap_gap') }} a
  on a.session_key = b.session_key and a.driver_code = b.attacker_code and a.lap_number = b.first_stop_lap - 1
left join {{ ref('fct_lap_gap') }} d
  on d.session_key = b.session_key and d.driver_code = b.defender_code and d.lap_number = b.first_stop_lap - 1
where a.position is null or d.position is null
   or a.position <= d.position
   or (b.margin_after_s > 0) <> b.attacker_ahead_after
   or b.second_stop_lap <= b.first_stop_lap
   or b.attacker_code = b.defender_code
