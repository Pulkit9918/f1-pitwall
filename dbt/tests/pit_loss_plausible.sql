{{ config(severity='warn') }}
-- A measured green-flag pit loss under 5 s or over 120 s is not a plausible stop; warn, do not fail.
select pit_loss_key, session_key, driver_code, in_lap, pit_loss_s
from {{ ref('fct_pit_loss') }}
where pit_loss_s < 5 or pit_loss_s > 120
