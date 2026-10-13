-- Silver: championship standings after each round (Jolpica round numbers).
select
    cast(season as integer)     as season,
    cast(round as integer)      as round,
    cast(position as integer)   as position,
    position_text,
    points,
    wins,
    driver_id,
    driver                      as driver_name,
    constructor                 as constructor_name
from {{ source('history', 'driver_standings') }}
