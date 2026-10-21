-- The gaps must agree with each other: the interval to the car ahead can never exceed the gap to the leader,
-- and the leader's gap is zero. Rows already flagged as disagreeing with the clock are not counted.
select lap_key
from {{ ref('fct_lap_gap') }}
where not order_disagrees_with_clock
  and (
       (interval_s is not null and gap_to_leader_s is not null and interval_s > gap_to_leader_s + 0.001)
    or (position = 1 and gap_to_leader_s <> 0)
  )
