-- One row per driver (FastF1 DriverId, or the ff1-<code> surrogate for practice-only drivers).
-- The code and name come from the driver's latest session; the name is the latest one that is not null.
select
    cast(driver_id as varchar)                                  as driver_id,
    cast(arg_max(driver_code, year * 100 + round) as varchar)   as driver_code,
    cast(arg_max(full_name, year * 100 + round)
         filter (where full_name is not null) as varchar)       as full_name,
    cast(arg_max(country_code, year * 100 + round) as varchar)  as country_code,
    cast(min(year) as integer)                                  as first_year,
    cast(max(year) as integer)                                  as last_year,
    cast(count(*) as bigint)                                    as sessions
from {{ ref('silver_results') }}
where driver_id is not null
group by driver_id
