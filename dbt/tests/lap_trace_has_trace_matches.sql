-- fct_lap_trace holds exactly the laps that fct_lap_trace_lap marks has_trace: none missing, none extra.
select coalesce(a.lap_key, b.lap_key) as lap_key, a.has_trace, b.lap_key is not null as in_trace
from {{ ref('fct_lap_trace_lap') }} as a
full join (select distinct lap_key from {{ ref('fct_lap_trace') }}) as b on b.lap_key = a.lap_key
where coalesce(a.has_trace, false) <> (b.lap_key is not null)
