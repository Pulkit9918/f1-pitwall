-- The length of each circuit layout as the position data measures it: the median, over clean laps whose position
-- samples cover the whole lap, of the x/y path length. Laps are scaled to this length so that any two laps can
-- be compared at the same distance.
-- The median is taken twice: laps more than 3% from the first median are thrown away and it is recomputed, so a
-- few sessions with bad positions (stray jumps, repeated samples) cannot move the reference. laps_measured is the
-- count before that trim and laps_used the count after. A layout is reliable when at least 20 laps survive, at least
-- 80% of the measured laps survive, and the spread (5th to 95th percentile, as a share of the median) is 3% or less;
-- a layout that is not gets no resampled laps. A layout where no laps survive the trim still has a row, with
-- laps_used 0 and null lengths.
with measured as (

    select
        d.circuit_layout_key,
        t.integrated_m
    from {{ ref('fct_lap_sample_total') }} as t
    join {{ ref('fct_lap') }} as l on l.lap_key = t.lap_key
    join {{ ref('dim_session_circuit') }} as d on d.session_key = t.session_key
    where l.is_clean_lap
      and d.circuit_layout_key is not null
      and t.first_gap_s <= {{ var('trace_max_edge_gap_s', 0.8) }}
      and t.last_gap_s <= {{ var('trace_max_edge_gap_s', 0.8) }}
      and t.max_gap_s <= {{ var('trace_max_gap_s', 1.5) }}

),

first_pass as (

    select circuit_layout_key, median(integrated_m) as first_median_m, count(*) as laps_measured
    from measured
    group by circuit_layout_key

),

trimmed as (

    select m.circuit_layout_key, m.integrated_m
    from measured as m
    join first_pass as f on f.circuit_layout_key = m.circuit_layout_key
    where abs(m.integrated_m / f.first_median_m - 1) <= 0.03

),

stats as (

    select
        circuit_layout_key,
        count(*)                              as laps_used,
        median(integrated_m)                  as ref_length_m,
        quantile_cont(integrated_m, 0.05)     as p05_m,
        quantile_cont(integrated_m, 0.95)     as p95_m
    from trimmed
    group by circuit_layout_key

)

select
    f.circuit_layout_key,
    cast(f.laps_measured as integer)                 as laps_measured,
    cast(coalesce(s.laps_used, 0) as integer)        as laps_used,
    s.ref_length_m,
    s.p05_m,
    s.p95_m,
    (s.p95_m - s.p05_m) / s.ref_length_m             as spread,
    coalesce(
        s.laps_used >= 20
        and s.laps_used >= 0.8 * f.laps_measured
        and (s.p95_m - s.p05_m) / s.ref_length_m <= 0.03,
        false)                                       as is_reliable
from first_pass as f
left join stats as s on s.circuit_layout_key = f.circuit_layout_key
