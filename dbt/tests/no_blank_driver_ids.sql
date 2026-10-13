{{ config(severity='warn') }}
-- Session results that still have no driver id after silver_results tried to fill it from the Jolpica history.
-- A warning to investigate: the row is kept in silver but left out of dim_driver.
select session_key, driver_code, full_name, driver_id
from {{ ref('silver_results') }}
where driver_id is null or lower(trim(driver_id)) in ('', 'nan')
