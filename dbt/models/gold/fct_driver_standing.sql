select
    season || '-' || lpad(cast(round as varchar), 2, '0') || '-' || driver_id   as standing_key,
    season,
    round,
    position,
    points,
    wins,
    driver_id,
    constructor_name
from {{ ref('silver_history_driver_standings') }}
