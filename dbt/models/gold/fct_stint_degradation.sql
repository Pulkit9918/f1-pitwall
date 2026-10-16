-- One row per driver stint in a dry race: tyre degradation in seconds lost per lap of tyre age.
--
-- Within a stint tyre age rises by one every lap, so the slope of lap time on lap number is
--   (lap-number trend) + (degradation).
-- The trend is fuel burn plus track evolution. experiments/tyre_probe.py measured it at -0.056 s
-- per lap (median over 131 dry races; by-season medians -0.052 to -0.060), so degradation is the
-- raw slope minus that constant. It does vary by race (middle half -0.067 to -0.044), a systematic
-- error of about +-0.012 s per lap for one race's stints; a per-circuit trend is the planned fix.
-- Override with --vars '{tyre_trend_s_per_lap: -0.05}'.
-- One stint's slope is also noisy (about +-0.02 s per lap); use medians over many stints.
--
-- Filters: race sessions without rain samples, clean laps (green, accurate, not deleted, not in or
-- out laps), SOFT/MEDIUM/HARD, laps slower than 107% of the session's fastest clean lap dropped,
-- stints with at least min_clean_laps clean laps spanning at least 8 laps.
with trend as (
    select cast({{ var('tyre_trend_s_per_lap', -0.056) }} as double) as s_per_lap
),

best as (
    select session_key, min(lap_time_s) as best_lap_s
    from {{ ref('fct_lap') }}
    where is_clean_lap
    group by session_key
),

clean as (
    select l.*
    from {{ ref('fct_lap') }} l
    join best b using (session_key)
    left join {{ ref('fct_session_weather') }} w using (session_key)
    where l.session_code = 'R'
      and l.is_clean_lap
      and l.compound in ('SOFT', 'MEDIUM', 'HARD')
      and l.stint is not null
      and l.lap_time_s <= 1.07 * b.best_lap_s
      and coalesce(w.share_of_samples_raining, 0) = 0
)

select
    c.session_key || '-' || c.driver_code || '-S' || cast(c.stint as varchar)    as stint_key,
    c.session_key,
    c.year,
    c.round,
    c.driver_code,
    c.stint,
    c.compound,
    count(*)                                                                      as clean_laps,
    min(c.tyre_life)                                                              as tyre_life_first,
    max(c.tyre_life)                                                              as tyre_life_last,
    regr_slope(c.lap_time_s, c.lap_number)                                        as raw_slope_s_per_lap,
    any_value(t.s_per_lap)                                                        as trend_s_per_lap,
    regr_slope(c.lap_time_s, c.lap_number) - any_value(t.s_per_lap)               as degradation_s_per_lap,
    regr_r2(c.lap_time_s, c.lap_number)                                           as slope_r2
from clean c
cross join trend t
group by c.session_key, c.year, c.round, c.driver_code, c.stint, c.compound
having count(*) >= {{ var('tyre_min_clean_laps', 8) }}
   and max(c.lap_number) - min(c.lap_number) >= 8
