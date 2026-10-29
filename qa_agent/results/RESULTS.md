# Question-answering agent: results

44 questions: 34 the data can answer and 10 it cannot. Answers are scored by running the agent's SQL and comparing the result table with a reference query (execution accuracy). A question the data cannot answer is correct only if the agent declines.

| Model | Run | Correct (answerable) | Declined correctly | Answered the unanswerable? | Declined the answerable | Right tables | Valid first try | Seconds per question |
|---|---|---|---|---|---|---|---|---|
| qwen2.5-coder:14b | 2026-10-29 | 26 of 34 (76%) | 8 of 10 | 2 | 1 of 34 | 76% | 85% | 10.149 |
| qwen2.5-coder:7b | 2026-10-29 | 15 of 34 (44%) | 9 of 10 | 1 | 1 of 34 | 76% | 82% | 6.259 |
| qwen2.5-coder:14b (first prompts) | 2026-10-29 | 13 of 34 (38%) | 10 of 10 | 0 | 14 of 34 | 44% | 56% | 6.473 |
| qwen2.5-coder:7b (first prompts) | 2026-10-29 | 9 of 34 (26%) | 9 of 10 | 1 | 11 of 34 | 53% | 68% | 5.111 |

## By category

| Category | qwen2.5-coder:14b | qwen2.5-coder:7b | qwen2.5-coder:14b (first prompts) | qwen2.5-coder:7b (first prompts) |
|---|---|---|---|---|
| aggregate | 4 of 7 | 3 of 7 | 4 of 7 | 3 of 7 |
| data-gap | 1 of 1 | 1 of 1 | 0 of 1 | 0 of 1 |
| history | 1 of 1 | 0 of 1 | 1 of 1 | 0 of 1 |
| join | 5 of 6 | 2 of 6 | 1 of 6 | 0 of 6 |
| lookup | 6 of 8 | 2 of 8 | 0 of 8 | 0 of 8 |
| project | 9 of 11 | 7 of 11 | 7 of 11 | 6 of 11 |
| unanswerable | 8 of 10 | 9 of 10 | 10 of 10 | 9 of 10 |

## Failures: qwen2.5-coder:14b (10)

- **grid_2024_sao_paulo** (lookup): Where did Max Verstappen start the 2024 São Paulo Grand Prix? Give the grid position.
  - got [['None']], expected [['17']]
- **laps_2025_norris_britain** (lookup): How many laps did Lando Norris complete in the 2025 British Grand Prix race?
  - got [['63']], expected [['52']]
- **hamilton_wins_2007_2024** (aggregate): How many Grands Prix did Lewis Hamilton win from 2007 to 2024 inclusive?
  - got [['43']], expected [['105']]
- **winners_2021** (aggregate): How many different drivers won a Grand Prix in 2021?
  - got [['8']], expected [['6']]
- **most_monaco_wins** (aggregate): Which driver has won the most Monaco Grands Prix? Give the driver id.
  - got [['leclerc', '4']], expected [['senna']]
- **race_laps_2025_singapore** (join): How many laps long was the 2025 Singapore Grand Prix race?
  - got [['1.2791267177417365']], expected [['62']]
- **safety_car_races_2024** (project): In how many 2024 Grand Prix races was there at least one safety car period (not counting virtual safety cars)?
  - got [['10']], expected [['8']]
- **sessions_loaded_per_year** (project): For each year from 2022 to 2024, how many sessions were loaded? Give the year and the count, in year order.
  - declined: no table chosen
- **stationary_time** (unanswerable): What was Lando Norris's stationary pit stop time in the 2025 Spanish Grand Prix?
  - answered anyway with `SELECT SUM(pit_lane_time_s) AS total_stationary_time_s FROM fct_pit_stop WHERE session_key IN (SELECT session_key FROM dim_session WHERE event ILIKE '%Spanish Grand Prix%' AND year = 2025 AND session_code = 'R') AND driver_code = 'NOR';` returning [['68.0039999999999']]
- **turn1_speed_2025_bahrain** (unanswerable): Which driver was fastest through Turn 1 in the 2025 Bahrain Grand Prix?
  - answered anyway with `SELECT d.full_name FROM fct_lap_sector ls JOIN dim_driver d ON ls.driver_code = d.driver_code JOIN dim_session s ON ls.session_key = s.session_key WHERE s.year = 2025 AND s.event ILIKE '%Bahrain%' AND ls.sector = 1 ORDER BY ls.time_s ASC LIMIT 1` returning [['George Russell']]

## Failures: qwen2.5-coder:7b (20)

- **winner_2025_italy** (lookup): Which driver won the 2025 Italian Grand Prix? Give the three-letter driver code.
  - got [], expected [['VER']]
- **pole_2025_monaco** (lookup): Who took pole position for the 2025 Monaco Grand Prix? Give the three-letter driver code.
  - got [], expected [['NOR']]
- **circuit_2024_belgium** (lookup): On which circuit was the 2024 Belgian Grand Prix run? Give the circuit name.
  - declined: The query cannot be executed because the table 'dim_circuit' is not found in the database.
- **grid_2024_sao_paulo** (lookup): Where did Max Verstappen start the 2024 São Paulo Grand Prix? Give the grid position.
  - got [['1'], ['None'], ['None']], expected [['17']]
- **laps_2025_norris_britain** (lookup): How many laps did Lando Norris complete in the 2025 British Grand Prix race?
  - got [['57']], expected [['52']]
- **front_row_2025_hungary** (lookup): Which drivers started on the front row (grid positions 1 and 2) of the 2025 Hungarian Grand Prix? Give the three-letter driver codes.
  - got [['LEC'], ['NOR']], expected [['LEC'], ['PIA']]
- **hamilton_wins_2007_2024** (aggregate): How many Grands Prix did Lewis Hamilton win from 2007 to 2024 inclusive?
  - no working query. Errors: Binder Error: Referenced column "session_code" not found in FROM clause!; Binder Error: Referenced column "session_code" not found in FROM clause!
- **races_2021** (aggregate): How many races were run in the 2021 season?
  - no working query. Errors: Binder Error: Referenced column "session_code" not found in FROM clause!; Binder Error: Referenced column "session_code" not found in FROM clause!
- **leclerc_podiums_2022** (aggregate): How many podium finishes did Charles Leclerc have in 2022?
  - got [['31']], expected [['11']]
- **driver_champion_2023** (aggregate): Which driver won the 2023 drivers' championship? Give the driver id.
  - got [['max_verstappen'], ['perez'], ['hamilton']], expected [['max_verstappen']]
- **fastest_lap_2025_abu_dhabi** (join): Who set the fastest race lap of the 2025 Abu Dhabi Grand Prix, and what was the time in seconds? Ignore deleted laps.
  - got [['Lando Norris', '82.167']], expected [['LEC', '86.725']]
- **race_laps_2025_singapore** (join): How many laps long was the 2025 Singapore Grand Prix race?
  - got [['88921.42100000002']], expected [['62']]
- **purple_ver_2025_italy_q** (join): How many purple sectors did Max Verstappen set in 2025 Italian Grand Prix qualifying?
  - got [['0']], expected [['3']]
- **compound_2025_spain** (join): Which tyre compound was used in the most stints in the 2025 Spanish Grand Prix race? Give the compound and the number of stints.
  - got [], expected [['SOFT', '51']]
- **spa_pit_loss** (project): What is the median green-flag pit loss at Spa, in seconds?
  - got [['None']], expected [['19.174500000000016']]
- **rain_races_2024** (project): In how many 2024 Grand Prix races did it rain at some point?
  - got [['24']], expected [['5']]
- **safety_car_races_2024** (project): In how many 2024 Grand Prix races was there at least one safety car period (not counting virtual safety cars)?
  - got [['13']], expected [['8']]
- **red_flags_2024** (project): Which 2024 Grand Prix races had a red flag? Give the event names.
  - got [['Japanese Grand Prix'], ['Italian Grand Prix'], ['Chinese Grand Prix']], expected [['São Paulo Grand Prix'], ['Monaco Grand Prix'], ['Japanese Grand Prix']]
- **champion_1988** (history): Who won the 1988 drivers' championship? Give the driver id.
  - got [['senna'], ['prost'], ['berger']], expected [['senna']]
- **turn1_speed_2025_bahrain** (unanswerable): Which driver was fastest through Turn 1 in the 2025 Bahrain Grand Prix?
  - answered anyway with `SELECT driver_code FROM fct_lap_sector WHERE session_key IN (SELECT session_key FROM dim_session WHERE event ILIKE '%Bahrain%' AND year = 2025 AND session_code = 'R') AND sector = 1 ORDER BY time_s ASC LIMIT 1` returning [['HAM']]

## Fresh question set

36 questions written after the prompts were frozen (28 answerable, 8 not), run once per model with no prompt changes afterwards.

| Model | Run | Prompts | Correct (answerable) | Declined correctly | Declined the answerable | Right tables | Valid first try | Seconds per question |
|---|---|---|---|---|---|---|---|---|
| qwen2.5-coder:14b | 2026-10-29 | v2 | 25 of 28 (89%) | 8 of 8 | 1 of 28 | 75% | 75% | 10.628 |
| qwen2.5-coder:7b | 2026-10-29 | v2 | 14 of 28 (50%) | 8 of 8 | 2 of 28 | 86% | 79% | 6.658 |

| Category | qwen2.5-coder:14b | qwen2.5-coder:7b |
|---|---|---|
| aggregate | 5 of 5 | 3 of 5 |
| history | 2 of 3 | 1 of 3 |
| join | 5 of 6 | 4 of 6 |
| lookup | 6 of 6 | 2 of 6 |
| project | 7 of 8 | 4 of 8 |
| unanswerable | 8 of 8 | 8 of 8 |

### Fresh set failures: qwen2.5-coder:14b (3)

- **f_senna_wins** (history): How many Grands Prix did Ayrton Senna win in his career?
  - declined: The provided tables do not contain information about Ayrton Senna's career results or wins.
- **f_race_laps_2024_bahrain** (join): How many laps long was the 2024 Bahrain Grand Prix race?
  - got [['2.6153696790138987']], expected [['57']]
- **f_safety_car_races_2025** (project): In how many 2025 Grand Prix races was there at least one safety car period (not counting virtual safety cars)?
  - got [['17']], expected [['12']]

### Fresh set failures: qwen2.5-coder:7b (14)

- **f_pole_2024_japan** (lookup): Who took pole position for the 2024 Japanese Grand Prix? Give the three-letter driver code.
  - got [], expected [['VER']]
- **f_grid_2025_austria_piastri** (lookup): Where did Oscar Piastri start the 2025 Austrian Grand Prix? Give the grid position.
  - got [['None'], ['None'], ['None']], expected [['3']]
- **f_circuit_2025_japan** (lookup): On which circuit was the 2025 Japanese Grand Prix run? Give the circuit name.
  - declined: The query requires the 'dim_circuit' table, which is not available in the provided schema.
- **f_laps_2024_spain_alonso** (lookup): How many laps did Fernando Alonso complete in the 2024 Spanish Grand Prix race?
  - got [['76']], expected [['65']]
- **f_races_2019** (aggregate): How many races were run in the 2019 season?
  - no working query. Errors: Binder Error: Referenced column "session_code" not found in FROM clause!; Binder Error: Referenced column "session_code" not found in FROM clause!
- **f_hamilton_podiums_2021** (aggregate): How many podium finishes did Lewis Hamilton have in 2021?
  - got [['36']], expected [['17']]
- **f_senna_wins** (history): How many Grands Prix did Ayrton Senna win in his career?
  - got [['0']], expected [['41']]
- **f_champion_1994** (history): Who won the 1994 drivers' championship? Give the driver id.
  - got [['michael_schumacher'], ['damon_hill'], ['berger']], expected [['michael_schumacher']]
- **f_fastest_lap_2024_italy** (join): Who set the fastest race lap of the 2024 Italian Grand Prix, and what was the time in seconds? Ignore deleted laps.
  - got [['ALO', '67.694']], expected [['NOR', '81.432']]
- **f_race_laps_2024_bahrain** (join): How many laps long was the 2024 Bahrain Grand Prix race?
  - got [['110450.63000000003']], expected [['57']]
- **f_monaco_pit_loss** (project): What is the median green-flag pit loss at Monaco, in seconds?
  - got [], expected [['21.251500000000007']]
- **f_coldest_race_2024** (project): Which 2024 Grand Prix race had the lowest average track temperature? Give the event name.
  - declined: The query cannot be executed because the column 'avg_track_temp' is not found in the FROM clause. The correct column name is 'avg_track_temp' in the table 'fct_session_weather'.
- **f_rain_races_2025** (project): In how many 2025 Grand Prix races did it rain at some point?
  - got [['16']], expected [['6']]
- **f_safety_car_races_2025** (project): In how many 2025 Grand Prix races was there at least one safety car period (not counting virtual safety cars)?
  - got [['17']], expected [['12']]
