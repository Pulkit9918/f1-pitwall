{{ config(severity='warn') }}
-- Do the FastF1 driver ids (dim_driver) exist in the Jolpica history (dim_historical_driver)?
-- This is a measurement: if the ids use different spellings the two driver tables cannot be joined
-- directly, and this test lists the ids that do not match.
select d.driver_id, d.driver_code, d.full_name
from {{ ref('dim_driver') }} d
left join {{ ref('dim_historical_driver') }} h on h.driver_id = d.driver_id
where h.driver_id is null
