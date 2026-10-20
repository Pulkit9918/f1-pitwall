-- Safety car, VSC and red flag periods per session, read from the wording of the race control messages.
-- This is the SQL version of build_periods in app/racecontrol.py, which stays as the reference: the walk
-- below reproduces it exactly (experiments/rc_periods_reconcile.py compares the two on the real lake).
-- One row per period. A period still running when the messages stop has no end (is_open).
-- Times are UTC timestamps for every session; the *_s columns (session seconds, like the lap tables)
-- exist only for sessions that have a session clock (silver_session_clock).
-- Messages in the same second are ordered by text. On the current lake the order does not change any
-- period (experiments/rc_ties.py), but a state machine like this is order-sensitive in principle.
with recursive
msgs as (
    select
        session_key,
        cast(message_time as timestamp)                                               as message_time,
        row_number() over (partition by session_key order by message_time, message)  as seq,
        (message_upper like '%BEHIND SAFETY CAR%' or message_upper like '%FORMATION%') as skip,
        ((coalesce(upper(flag), '') = 'RED' or message_upper like 'RED FLAG%')
            and message_upper not like '%INFRINGEMENT%')                              as is_red,
        (message_upper like '%SAFETY CAR DEPLOYED%' and message_upper not like '%VIRTUAL%') as is_sc,
        (message_upper like '%VSC DEPLOYED%' or message_upper like '%VIRTUAL SAFETY CAR DEPLOYED%') as is_vsc,
        (message_upper like '%VSC ENDING%' or message_upper like '%VIRTUAL SAFETY CAR ENDING%') as is_vsc_end,
        (message_upper like '%PIT EXIT OPEN%' or message_upper like '%TRACK CLEAR%'
            or message_upper like '%RACE START%')                                     as is_reopen,
        message_upper like '%LIGHTS OFF%'                                             as is_lights_off,
        message_upper like '%IN THIS LAP%'                                            as is_in_this_lap,
        message_upper like '%TRACK CLEAR%'                                            as is_track_clear
    from {{ ref('silver_race_control') }}
),

walk as (
    select session_key, 0 as seq, cast(null as timestamp) as message_time,
           'NONE' as state_before, 0 as period_before, false as close_flag,
           cast(null as varchar) as open_kind, cast(null as varchar) as sc_mark,
           'NONE' as state_after, 0 as period_after
    from (select distinct session_key from msgs)

    union all

    select a.session_key, a.seq, a.message_time, a.state_before, a.period_before,
           a.close_flag, a.open_kind, a.sc_mark,
           case when a.open_kind is not null then a.open_kind
                when a.close_flag then 'NONE'
                else a.state_before end                                         as state_after,
           a.period_before + case when a.open_kind is not null then 1 else 0 end as period_after
    from (
        select
            m.session_key, m.seq, m.message_time,
            w.state_after  as state_before,
            w.period_after as period_before,
            case
                when m.skip then false
                when m.is_red then w.state_after not in ('RED', 'NONE')
                when w.state_after = 'RED' then (m.is_sc or m.is_reopen)
                when m.is_sc or m.is_vsc then w.state_after <> 'NONE'
                when w.state_after = 'SC'
                    then (m.is_track_clear and not m.is_lights_off and not m.is_in_this_lap)
                when w.state_after = 'VSC' then m.is_vsc_end
                else false
            end as close_flag,
            case
                when m.skip then null
                when m.is_red then case when w.state_after = 'RED' then null else 'RED' end
                when w.state_after = 'RED'
                    then case when m.is_sc then 'SC' when m.is_reopen and m.is_vsc then 'VSC' end
                when m.is_sc then 'SC'
                when m.is_vsc then 'VSC'
            end as open_kind,
            case
                when w.state_after = 'SC' and not m.skip and not m.is_red and not m.is_sc and not m.is_vsc
                    then case when m.is_lights_off then 'OFF' when m.is_in_this_lap then 'IN' end
            end as sc_mark
        from walk w
        join msgs m on m.session_key = w.session_key and m.seq = w.seq + 1
    ) a
),

opened as (
    select session_key, period_after as period_no, open_kind as kind, message_time as start_time
    from walk where open_kind is not null
),
closed as (
    select session_key, period_before as period_no, message_time as end_time
    from walk where close_flag
),
marks as (
    select session_key, period_before as period_no,
           min(case when sc_mark = 'IN'  then message_time end) as pit_in_time,
           min(case when sc_mark = 'OFF' then message_time end) as lights_off_time
    from walk where sc_mark is not null
    group by 1, 2
),
sessions as (
    select distinct session_key, year, round, session_code from {{ ref('silver_race_control') }}
),
periods as (
    select o.session_key, o.period_no, o.kind, o.start_time, c.end_time,
           (c.end_time is null) as is_open, m.pit_in_time, m.lights_off_time
    from opened o
    left join closed c using (session_key, period_no)
    left join marks m using (session_key, period_no)
    where c.end_time is null or c.end_time > o.start_time
)

select
    p.session_key || '-' || cast(p.period_no as varchar)                  as period_key,
    p.session_key,
    s.year,
    s.round,
    s.session_code,
    p.period_no,
    p.kind,
    p.start_time,
    p.end_time,
    p.is_open,
    p.pit_in_time,
    p.lights_off_time,
    epoch(p.start_time)      - k.session_zero_epoch_s                      as start_s,
    epoch(p.end_time)        - k.session_zero_epoch_s                      as end_s,
    epoch(p.pit_in_time)     - k.session_zero_epoch_s                      as pit_in_s,
    epoch(p.lights_off_time) - k.session_zero_epoch_s                      as lights_off_s,
    (k.session_key is not null)                                            as has_session_clock
from periods p
join sessions s using (session_key)
left join {{ ref('silver_session_clock') }} k using (session_key)
