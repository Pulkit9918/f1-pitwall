{{ config(severity='warn') }}
-- Warns about circuit layouts that have at least 20 measured laps but are not reliable: fewer than 80% of the laps
-- survive the 3% trim, or the spread is above 3%. The length comes from the x/y path, which should agree within a
-- percent or so from lap to lap, so this means a wrong share of the position data for that layout is bad (a layout
-- change under one name, a bad session outnumbering the good ones).
select circuit_layout_key, laps_measured, laps_used, ref_length_m, spread
from {{ ref('dim_layout_length') }}
where laps_measured >= 20 and not is_reliable
