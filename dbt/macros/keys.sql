{#- Natural session key, e.g. 2025-R07-R. Round numbers are FastF1's, not the official calendar's. -#}
{% macro session_key(year, round, session_code) -%}
    (cast({{ year }} as varchar) || '-R' || lpad(cast({{ round }} as varchar), 2, '0') || '-' || {{ session_code }})
{%- endmacro %}
