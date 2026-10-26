-- One row per timed sector of a lap, with the colour the timing screens would have shown when the sector was
-- completed: purple if it beat every earlier time in the session in that sector (any driver), green if it beat the
-- driver's own earlier times, yellow otherwise. The first time anyone sets in a sector is purple, and the first time
-- for a driver is green, as on the broadcast.
-- Order is by the session clock at which the sector finished: lap start plus the sectors so far. A sector counts only
-- if the lap was not deleted, the lap started on a known clock time, and this and every earlier sector of the lap has a
-- time, since otherwise its place in the order is unknown. A time equal to the best is not an improvement (not purple).
-- best_before_s and own_best_before_s are the times it was compared with, null when there was none.
with laps as (

    select
        session_key, lap_key, year, round, session_code, driver_code, lap_number, lap_start_time_s,
        sector1_s, sector2_s, sector3_s
    from {{ ref('fct_lap') }}
    where not coalesce(deleted, false)
      and lap_start_time_s is not null

),

sectors as (

    select session_key, lap_key, year, round, session_code, driver_code, lap_number,
           cast(1 as smallint) as sector, sector1_s as time_s, lap_start_time_s + sector1_s as completed_at_s
    from laps
    where sector1_s > 0

    union all

    select session_key, lap_key, year, round, session_code, driver_code, lap_number,
           cast(2 as smallint), sector2_s, lap_start_time_s + sector1_s + sector2_s
    from laps
    where sector1_s > 0 and sector2_s > 0

    union all

    select session_key, lap_key, year, round, session_code, driver_code, lap_number,
           cast(3 as smallint), sector3_s, lap_start_time_s + sector1_s + sector2_s + sector3_s
    from laps
    where sector1_s > 0 and sector2_s > 0 and sector3_s > 0

),

compared as (

    select
        *,
        min(time_s) over (
            partition by session_key, sector order by completed_at_s, lap_key
            rows between unbounded preceding and 1 preceding
        ) as best_before_s,
        min(time_s) over (
            partition by session_key, driver_code, sector order by completed_at_s, lap_key
            rows between unbounded preceding and 1 preceding
        ) as own_best_before_s
    from sectors

)

select
    lap_key,
    session_key,
    cast(year as integer)       as year,
    cast(round as integer)      as round,
    cast(session_code as varchar) as session_code,
    driver_code,
    cast(lap_number as integer) as lap_number,
    sector,
    cast(time_s as double)          as time_s,
    cast(completed_at_s as double)  as completed_at_s,
    cast(case
        when best_before_s is null or time_s < best_before_s then 'purple'
        when own_best_before_s is null or time_s < own_best_before_s then 'green'
        else 'yellow'
    end as varchar)                 as status,
    cast(best_before_s as double)     as best_before_s,
    cast(own_best_before_s as double) as own_best_before_s
from compared
