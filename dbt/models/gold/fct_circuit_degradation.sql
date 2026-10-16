-- Tyre degradation per circuit layout and compound: the median over every dry-race stint there.
--
-- Built from fct_stint_degradation, where one stint's figure is noisy (about +-0.02 s per lap), so a
-- circuit's figure is only as good as the number of stints behind it. approx_se_median_s_per_lap is
-- 1.2533 * standard deviation / sqrt(stints), the standard error of a median if stints were
-- independent and roughly normal; it is a guide, not a guarantee. is_reliable is true only with at
-- least tyre_min_stints stints from at least tyre_min_races races (defaults 20 and 3, a judgement
-- call, override with --vars). The trend behind each stint scales with the race's median lap time
-- (a line fitted over 118 races). Leave-one-circuit-out (experiments/trend_loco.py) cut the robust
-- trend error from 0.0206 to 0.0081 s per lap, but Jeddah and Las Vegas stay understated (about
-- 0.028 and 0.017) and Marina Bay overstated (about 0.019), from 3 to 5 races each. is_reliable does
-- not detect this, and a circuit-specific difference is a bias that more stints do not remove.
select
    c.circuit_layout_key || '-' || d.compound                                     as circuit_compound_key,
    c.circuit_layout_key,
    c.circuit_id,
    c.layout_id,
    c.circuit_name,
    d.compound,
    count(*)                                                                      as stints,
    count(distinct d.session_key)                                                 as races,
    count(distinct d.year)                                                        as seasons,
    median(d.degradation_s_per_lap)                                               as median_degradation_s_per_lap,
    quantile_cont(d.degradation_s_per_lap, 0.25)                                  as p25_degradation_s_per_lap,
    quantile_cont(d.degradation_s_per_lap, 0.75)                                  as p75_degradation_s_per_lap,
    1.2533 * stddev_samp(d.degradation_s_per_lap) / sqrt(count(*))                as approx_se_median_s_per_lap,
    (count(*) >= {{ var('tyre_min_stints', 20) }}
        and count(distinct d.session_key) >= {{ var('tyre_min_races', 3) }})      as is_reliable
from {{ ref('fct_stint_degradation') }} d
join {{ ref('dim_session_circuit') }} c
    on c.session_key = d.session_key
group by c.circuit_layout_key, c.circuit_id, c.layout_id, c.circuit_name, d.compound
