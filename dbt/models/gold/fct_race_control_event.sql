-- One row per race control message with a coarse event type.
-- Only classification lives here. The safety-car / VSC / red-flag *periods* are still computed
-- in app/racecontrol.py; moving that logic into SQL is a later step.
select
    event_key,
    session_key,
    year,
    round,
    session_code,
    message_time,
    lap_number,
    category,
    flag,
    scope,
    sector,
    message,
    case
        when (flag = 'RED' or message_upper like 'RED FLAG%')
             and message_upper not like '%INFRINGEMENT%'               then 'RED_FLAG'
        when message_upper like '%VIRTUAL SAFETY CAR DEPLOYED%'
             or message_upper like '%VSC DEPLOYED%'                    then 'VSC_DEPLOYED'
        when message_upper like '%VIRTUAL SAFETY CAR ENDING%'
             or message_upper like '%VSC ENDING%'                      then 'VSC_ENDING'
        when message_upper like '%SAFETY CAR DEPLOYED%'                then 'SC_DEPLOYED'
        when flag = 'CHEQUERED'                                        then 'CHEQUERED'
        when message_upper like '%DELETED%'                            then 'LAP_DELETED'
        when message_upper like 'FIA STEWARDS:%'
             and message_upper like '%PENALTY%'                        then 'PENALTY'
        when message_upper like 'FIA STEWARDS:%'
             and message_upper like '%INVESTIGAT%'                     then 'INVESTIGATION'
        else 'OTHER'
    end                                                                as event_type
from {{ ref('silver_race_control') }}
