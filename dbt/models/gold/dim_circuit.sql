select
    cast(circuit_id as varchar)     as circuit_id,
    cast(circuit_name as varchar)   as circuit_name,
    cast(locality as varchar)       as locality,
    cast(country as varchar)        as country,
    cast(lat as double)             as lat,
    cast("long" as double)          as long
from {{ source('history', 'circuits') }}
