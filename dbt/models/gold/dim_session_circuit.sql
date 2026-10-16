-- One row per session with its physical circuit and track layout.
-- circuit_id is Jolpica's id for the same year and round, so event names that change between seasons
-- (Mexican / Mexico City, Brazilian / Sao Paulo, Bahrain GP held in Malaysia in 2026) map to one circuit.
-- layout_id marks eras in which the track itself changed (seed circuit_layouts); a circuit that is not
-- in the seed has a single layout, 'v1'. A seed range is year * 100 + round.
with race as (
    select season as year, round, min(circuit_id) as circuit_id
    from {{ ref('fct_season_result') }}
    group by season, round
)

select
    s.session_key,
    s.year,
    s.round,
    s.session_code,
    s.event,
    r.circuit_id,
    c.circuit_name,
    c.country,
    coalesce(l.layout_id, 'v1')                                   as layout_id,
    r.circuit_id || ':' || coalesce(l.layout_id, 'v1')            as circuit_layout_key
from {{ ref('dim_session') }} s
left join race r
    on r.year = s.year and r.round = s.round
left join {{ ref('dim_circuit') }} c
    on c.circuit_id = r.circuit_id
left join {{ ref('circuit_layouts') }} l
    on l.circuit_id = r.circuit_id
   and s.year * 100 + s.round between l.from_key and l.to_key
qualify row_number() over (
    partition by s.session_key order by l.to_key - l.from_key asc nulls last
) = 1
