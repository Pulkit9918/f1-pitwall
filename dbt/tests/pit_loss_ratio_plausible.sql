{{ config(severity='warn') }}
-- A stop under a safety car or VSC should cost less than a green-flag stop, because the field is slow while the
-- pit lane is not. Warns if a measured ratio falls outside 0.2 to 1.0 (and has at least 30 stops behind it).
select regime, ratio_to_green
from {{ ref('fct_pit_loss_ratio') }}
where regime <> 'green' and is_reliable
  and (ratio_to_green < 0.2 or ratio_to_green > 1.0)
