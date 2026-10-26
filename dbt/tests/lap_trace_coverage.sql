{{ config(severity='warn') }}
-- Warns about sessions where fewer than half of the clean laps got a distance trace, which usually means the
-- telemetry for that session is thin or ends early rather than anything about the cars. Only sessions with at
-- least 100 clean laps are judged, so a tiny test lake does not trigger it.
select
    l.session_key,
    count(*)                                           as clean_laps,
    avg(case when t.has_trace then 1.0 else 0.0 end)   as share_with_trace
from {{ ref('fct_lap_trace_lap') }} as t
join {{ ref('fct_lap') }} as l on l.lap_key = t.lap_key
where l.is_clean_lap
group by l.session_key
having count(*) >= 100
   and avg(case when t.has_trace then 1.0 else 0.0 end) < 0.5
