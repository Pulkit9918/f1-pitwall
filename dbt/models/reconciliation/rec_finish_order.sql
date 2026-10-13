-- Cross-source reconciliation of the laps data against the official classification, per race or sprint.
-- The checks run on classified finishers (status Finished or +N lap). Retirees legitimately differ:
-- the laps data holds the partial lap they stopped on, some have no official lap count, and
-- disqualified drivers keep their laps. They are reported separately and never fail a test.
--   pair_agreement_pct       share of finisher pairs in the same relative order on track and officially;
--                            one post-race penalty costs a few pairs, not a whole grid of positions
--   finisher_laps_agree_pct  share of finishers whose lap count equals official laps completed
--   penalty_events           penalty-related stewards messages in the session (context, not a cause)
with last_pos as (
    select session_key, driver_code, position as lap_position
    from {{ ref('fct_lap') }}
    where session_code in ('R', 'S') and position is not null
    qualify row_number() over (
        partition by session_key, driver_code order by lap_number desc
    ) = 1
),

laps_run as (
    select session_key, driver_code, max(lap_number) as laps_run
    from {{ ref('fct_lap') }}
    where session_code in ('R', 'S')
    group by session_key, driver_code
),

compared as (
    select
        l.session_key,
        l.driver_code,
        l.lap_position,
        r.position as official_position,
        r.laps_completed,
        b.laps_run,
        (r.status = 'Finished' or r.status like '+%') as is_finisher
    from last_pos l
    join {{ ref('fct_result') }} r
        on r.session_key = l.session_key and r.driver_code = l.driver_code
    join laps_run b
        on b.session_key = l.session_key and b.driver_code = l.driver_code
    where r.position is not null
),

by_session as (
    select
        session_key,
        count(*)                                                            as drivers_compared,
        count(*) filter (where is_finisher)                                 as finishers,
        count(*) filter (where is_finisher and laps_run = laps_completed)   as finisher_laps_agree,
        count(*) filter (where not is_finisher)                             as non_finishers,
        count(*) filter (where not is_finisher
                         and laps_run - laps_completed in (0, 1))           as non_finisher_laps_within_one
    from compared
    group by session_key
),

pairs as (
    select
        a.session_key,
        count(*)                                                            as pairs,
        count(*) filter (where a.lap_position < b.lap_position)             as concordant
    from compared a
    join compared b
        on  a.session_key = b.session_key
        and a.official_position < b.official_position
    where a.is_finisher and b.is_finisher
    group by a.session_key
),

penalties as (
    select session_key, count(*) as penalty_events
    from {{ ref('fct_race_control_event') }}
    where event_type = 'PENALTY'
    group by session_key
)

select
    s.session_key,
    s.drivers_compared,
    s.finishers,
    round(100.0 * p.concordant / nullif(p.pairs, 0), 1)                     as pair_agreement_pct,
    round(100.0 * s.finisher_laps_agree / nullif(s.finishers, 0), 1)        as finisher_laps_agree_pct,
    s.finishers - s.finisher_laps_agree                                     as finisher_laps_mismatch,
    s.non_finishers,
    round(100.0 * s.non_finisher_laps_within_one / nullif(s.non_finishers, 0), 1)
                                                                            as non_finisher_laps_within_one_pct,
    coalesce(n.penalty_events, 0)                                           as penalty_events
from by_session s
left join pairs p using (session_key)
left join penalties n using (session_key)
