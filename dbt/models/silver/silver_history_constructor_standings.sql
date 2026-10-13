-- Silver: constructor standings after each round (Jolpica round numbers).
select
    cast(season as integer)     as season,
    cast(round as integer)      as round,
    cast(position as integer)   as position,
    points,
    wins,
    constructor_id,
    constructor                 as constructor_name,
    nationality
from {{ source('history', 'constructor_standings') }}
