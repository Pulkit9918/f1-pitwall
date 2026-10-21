-- A stop can never gain places and a slower stop can never lose fewer: predicted position is at least the
-- current position, and fast <= middle <= slow. Rows with no prediction (red flag) are not counted.
select pit_now_key
from {{ ref('fct_pit_now') }}
where predicted_position is not null
  and (predicted_position < position_now
       or predicted_position_fast > predicted_position
       or predicted_position > predicted_position_slow)
