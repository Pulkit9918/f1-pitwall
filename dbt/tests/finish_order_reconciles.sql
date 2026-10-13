{{ config(severity='warn') }}
-- Races where, among classified finishers, the order on track differs from the official classification
-- (under 90% of pairs in the same order) or more than one finisher has a lap count that differs from
-- the official laps completed. Needs at least 10 finishers. Thresholds are first guesses.
-- A warning to investigate (often a post-race penalty or a red-flag restart), not a failure.
select session_key, finishers, pair_agreement_pct, finisher_laps_mismatch, penalty_events
from {{ ref('rec_finish_order') }}
where finishers >= 10
  and (pair_agreement_pct < 90 or finisher_laps_mismatch > 1)
