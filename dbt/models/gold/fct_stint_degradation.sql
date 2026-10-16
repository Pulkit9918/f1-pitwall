-- One row per driver stint in a dry race: tyre degradation in seconds lost per lap of tyre age.
--
-- Within a stint tyre age rises by one every lap, so the slope of lap time on lap number is
--   (lap-number trend) + (degradation).
-- The trend is fuel burn plus track evolution. It scales with lap length: across 118 dry races
-- (red-flag and badly determined fits dropped) a Theil-Sen fit of the probe's trend on each race's
-- median clean lap gave trend = -0.00118 * lap_s + 0.0514, cutting the unexplained robust spread
-- from 0.0181 to 0.0077 s per lap (a single constant was -0.054). Degradation is the raw slope
-- minus this per-race trend. The line was fitted in-sample and is least certain at very short or
-- very long laps. For a constant trend again, override with
-- --vars '{tyre_trend_slope_per_lap_s: 0, tyre_trend_intercept_s_per_lap: -0.056}'.
-- One stint's slope is also noisy (about +-0.02 s per lap); use medians over many stints.
--
-- Filters: race sessions without rain samples, clean laps (green, accurate, not deleted, not in or
-- out laps), SOFT/MEDIUM/HARD, laps slower than 107% of the session's fastest clean lap dropped,
-- stints with at least min_clean_laps clean laps spanning at least 8 laps.
with trend as (
    select cast({{ var('tyre_trend_slope_per_lap_s', -0.00118) }} as double)   as slope,
           cast({{ var('tyre_trend_intercept_s_per_lap', 0.0514) }} as double) as intercept
),

best as (
    select session_key, min(lap_time_s) as best_lap_s, median(lap_time_s) as median_lap_s
    from {{ ref('fct_lap') }}
    where is_clean_lap
    group by session_key
),

clean as (
    select l.*, b.median_lap_s
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
    any_value(c.median_lap_s)                                                     as median_clean_lap_s,
    any_value(t.slope) * any_value(c.median_lap_s) + any_value(t.intercept)       as trend_s_per_lap,
    regr_slope(c.lap_time_s, c.lap_number)
        - (any_value(t.slope) * any_value(c.median_lap_s) + any_value(t.intercept)) as degradation_s_per_lap,
    regr_r2(c.lap_time_s, c.lap_number)                                           as slope_r2
from clean c
cross join trend t
group by c.session_key, c.year, c.round, c.driver_code, c.stint, c.compound
having count(*) >= {{ var('tyre_min_clean_laps', 8) }}
   and max(c.lap_number) - min(c.lap_number) >= 8
