-- Every driver in the Jolpica history (1950 to now). dim_driver covers the FastF1 era only.
select
    cast(driver_id as varchar)                              as driver_id,
    cast(given_name as varchar)                             as given_name,
    cast(family_name as varchar)                            as family_name,
    cast(given_name || ' ' || family_name as varchar)       as full_name,
    cast(try_cast(date_of_birth as date) as date)           as date_of_birth,
    cast(nationality as varchar)                            as nationality,
    cast(code as varchar)                                   as driver_code,
    cast(number as integer)                                 as car_number
from {{ source('history', 'drivers') }}
