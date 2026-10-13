select
    cast(constructor_id as varchar) as constructor_id,
    cast(name as varchar)           as name,
    cast(nationality as varchar)    as nationality
from {{ source('history', 'constructors') }}
