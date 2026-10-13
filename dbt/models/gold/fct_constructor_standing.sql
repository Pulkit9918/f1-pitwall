select
    season || '-' || lpad(cast(round as varchar), 2, '0') || '-' || constructor_id  as standing_key,
    season,
    round,
    position,
    points,
    wins,
    constructor_id
from {{ ref('silver_history_constructor_standings') }}
