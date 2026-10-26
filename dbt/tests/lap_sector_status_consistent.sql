-- The sector colours agree with their own definition, checked three ways that do not repeat the model's window.
--   compared    a purple sector beat the best before it; a green or yellow one did not beat the best before it, and a
--               yellow one did not beat the driver's own best before it
--   purple_run  the purple times of a session sector get strictly shorter as the session goes on
--   green_run   the purple and green times of a driver's sector get strictly shorter as the session goes on
--   session_best  the last purple of a session sector is the quickest time of that sector
with s as (select * from {{ ref('fct_lap_sector') }}),

compared as (

    select lap_key, sector, 'compared' as problem from s
    where (status = 'purple' and best_before_s is not null and time_s >= best_before_s)
       or (status <> 'purple' and (best_before_s is null or time_s < best_before_s))
       or (status = 'yellow' and (own_best_before_s is null or time_s < own_best_before_s))
       or (status = 'green' and own_best_before_s is not null and time_s >= own_best_before_s)

),

purple_run as (

    select lap_key, sector, 'purple_run' as problem from (
        select lap_key, sector, time_s,
               lag(time_s) over (partition by session_key, sector order by completed_at_s, lap_key) as prev_s
        from s where status = 'purple'
    ) where prev_s is not null and time_s >= prev_s

),

green_run as (

    select lap_key, sector, 'green_run' as problem from (
        select lap_key, sector, time_s,
               lag(time_s) over (partition by session_key, driver_code, sector order by completed_at_s, lap_key) as prev_s
        from s where status in ('purple', 'green')
    ) where prev_s is not null and time_s >= prev_s

),

session_best as (

    select a.session_key as lap_key, a.sector, 'session_best' as problem
    from (select session_key, sector, min(time_s) as best from s group by 1, 2) as a
    where not exists (
        select 1 from s where s.session_key = a.session_key and s.sector = a.sector and s.status = 'purple' and s.time_s = a.best
    )

)

select * from compared
union all select * from purple_run
union all select * from green_run
union all select * from session_best
