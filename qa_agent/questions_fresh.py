"""A second question set, written after the prompts were frozen, to measure the agent without tuning to the questions.

Same format and categories as questions.py, but different drivers, races, years and tables, and no question was run
against a model before the prompts were fixed. Run it with:  python -m qa_agent.run_eval --set fresh --model <name>
"""
from .questions import J_RES, RACE, Q

FRESH = [
    # ---- lookups
    Q("f_winner_2023_monaco", "lookup", "Which driver won the 2023 Monaco Grand Prix? Give the three-letter driver code.",
      f"select r.driver_code {J_RES} where s.year = 2023 and {RACE} and s.event ilike '%Monaco%' and r.position = 1",
      ["fct_result", "dim_session"]),
    Q("f_pole_2024_japan", "lookup", "Who took pole position for the 2024 Japanese Grand Prix? Give the three-letter driver code.",
      f"select r.driver_code {J_RES} where s.year = 2024 and s.session_code = 'Q' and s.event ilike '%Japanese%' and r.position = 1",
      ["fct_result", "dim_session"]),
    Q("f_team_2025_canada_hamilton", "lookup", "Which team did Lewis Hamilton drive for in the 2025 Canadian Grand Prix? Give the team name.",
      f"select r.team_name {J_RES} where s.year = 2025 and {RACE} and s.event ilike '%Canadian%' and r.driver_code = 'HAM'",
      ["fct_result", "dim_session"]),
    Q("f_grid_2025_austria_piastri", "lookup", "Where did Oscar Piastri start the 2025 Austrian Grand Prix? Give the grid position.",
      f"select r.grid_position {J_RES} where s.year = 2025 and {RACE} and s.event ilike '%Austrian%' and r.driver_code = 'PIA'",
      ["fct_result", "dim_session"]),
    Q("f_circuit_2025_japan", "lookup", "On which circuit was the 2025 Japanese Grand Prix run? Give the circuit name.",
      f"select s.circuit_name from dim_session_circuit s where s.year = 2025 and {RACE} and s.event ilike '%Japanese%'",
      ["dim_session_circuit"]),
    Q("f_laps_2024_spain_alonso", "lookup", "How many laps did Fernando Alonso complete in the 2024 Spanish Grand Prix race?",
      f"select r.laps_completed {J_RES} where s.year = 2024 and {RACE} and s.event ilike '%Spanish%' and r.driver_code = 'ALO'",
      ["fct_result", "dim_session"]),
    # ---- aggregates
    Q("f_verstappen_wins_2023", "aggregate", "How many Grands Prix did Max Verstappen win in 2023?",
      "select count(*) from fct_season_result where season = 2023 and driver_id = 'max_verstappen' and is_win",
      ["fct_season_result"]),
    Q("f_races_2019", "aggregate", "How many races were run in the 2019 season?",
      "select count(distinct round) from fct_season_result where season = 2019", ["fct_season_result"]),
    Q("f_hamilton_podiums_2021", "aggregate", "How many podium finishes did Lewis Hamilton have in 2021?",
      "select count(*) from fct_season_result where season = 2021 and driver_id = 'hamilton' and is_podium",
      ["fct_season_result"]),
    Q("f_most_wins_2022", "aggregate", "Which driver won the most Grands Prix in 2022? Give the driver id.",
      "select driver_id from fct_season_result where season = 2022 and is_win group by driver_id order by count(*) desc, driver_id limit 1",
      ["fct_season_result"], note="check_reference prints the top three so a tie can be spotted"),
    Q("f_most_british_wins", "aggregate", "Which driver has won the most British Grands Prix? Give the driver id.",
      "select driver_id from fct_season_result where circuit_id = 'silverstone' and is_win group by driver_id order by count(*) desc, driver_id limit 1",
      ["fct_season_result"], note="check_reference prints the top three so a tie can be spotted"),
    # ---- history
    Q("f_senna_wins", "history", "How many Grands Prix did Ayrton Senna win in his career?",
      "select count(*) from fct_season_result where driver_id = 'senna' and is_win", ["fct_season_result"]),
    Q("f_champion_1994", "history", "Who won the 1994 drivers' championship? Give the driver id.",
      "select driver_id from fct_driver_standing where season = 1994 and "
      "round = (select max(round) from fct_driver_standing where season = 1994) and position = 1",
      ["fct_driver_standing"]),
    Q("f_constructor_champion_2010", "history", "Which constructor won the 2010 constructors' championship? Give the constructor id.",
      "select constructor_id from fct_constructor_standing where season = 2010 and "
      "round = (select max(round) from fct_constructor_standing where season = 2010) and position = 1",
      ["fct_constructor_standing"]),
    # ---- joins and laps
    Q("f_fastest_lap_2024_italy", "join", "Who set the fastest race lap of the 2024 Italian Grand Prix, and what was the time in seconds? Ignore deleted laps.",
      f"select l.driver_code, l.lap_time_s from fct_lap l join dim_session s on s.session_key = l.session_key "
      f"where s.year = 2024 and {RACE} and s.event ilike '%Italian%' and not coalesce(l.deleted, false) "
      f"and l.lap_time_s is not null order by l.lap_time_s limit 1",
      ["fct_lap", "dim_session"], tol=0.001),
    Q("f_race_laps_2024_bahrain", "join", "How many laps long was the 2024 Bahrain Grand Prix race?",
      f"select max(l.lap_number) from fct_lap l join dim_session s on s.session_key = l.session_key "
      f"where s.year = 2024 and {RACE} and s.event ilike '%Bahrain%'",
      ["fct_lap", "dim_session"]),
    Q("f_leader_lap30_2025_spain", "join", "Who led the 2025 Spanish Grand Prix race at the end of lap 30? Give the three-letter driver code.",
      f"select g.driver_code from fct_lap_gap g join dim_session s on s.session_key = g.session_key "
      f"where s.year = 2025 and {RACE} and s.event ilike '%Spanish%' and g.lap_number = 30 and g.position = 1",
      ["fct_lap_gap", "dim_session"]),
    Q("f_stops_2025_monaco_leclerc", "join", "How many pit stops did Charles Leclerc make in the 2025 Monaco Grand Prix race?",
      f"select count(*) from fct_pit_stop p join dim_session s on s.session_key = p.session_key "
      f"where s.year = 2025 and {RACE} and s.event ilike '%Monaco%' and p.driver_code = 'LEC' and p.is_race_session",
      ["fct_pit_stop", "dim_session"]),
    Q("f_purple_nor_2024_belgium_q", "join", "How many purple sectors did Lando Norris set in 2024 Belgian Grand Prix qualifying?",
      "select count(*) from fct_lap_sector x join dim_session s on s.session_key = x.session_key "
      "where s.year = 2024 and s.session_code = 'Q' and s.event ilike '%Belgian%' and x.driver_code = 'NOR' and x.status = 'purple'",
      ["fct_lap_sector", "dim_session"]),
    Q("f_hard_stints_2024_bahrain", "join", "How many stints were run on the HARD compound in the 2024 Bahrain Grand Prix race?",
      f"select count(*) from fct_stint f join dim_session s on s.session_key = f.session_key "
      f"where s.year = 2024 and {RACE} and s.event ilike '%Bahrain%' and f.compound = 'HARD'",
      ["fct_stint", "dim_session"]),
    # ---- the project's own models
    Q("f_lowest_pit_loss_circuit", "project", "Which circuit has the lowest median green-flag pit loss, counting only circuits marked reliable? Give the circuit name.",
      "select circuit_name from fct_circuit_pit_loss where is_reliable order by median_pit_loss_s asc limit 1",
      ["fct_circuit_pit_loss"]),
    Q("f_monaco_pit_loss", "project", "What is the median green-flag pit loss at Monaco, in seconds?",
      "select median_pit_loss_s from fct_circuit_pit_loss where circuit_name ilike '%Monaco%'", ["fct_circuit_pit_loss"]),
    Q("f_coldest_race_2024", "project", "Which 2024 Grand Prix race had the lowest average track temperature? Give the event name.",
      f"select s.event from fct_session_weather w join dim_session s on s.session_key = w.session_key "
      f"where s.year = 2024 and {RACE} order by w.avg_track_temp asc limit 1",
      ["fct_session_weather", "dim_session"]),
    Q("f_rain_races_2025", "project", "In how many 2025 Grand Prix races did it rain at some point?",
      "select count(*) from fct_session_weather w where w.year = 2025 and w.session_code = 'R' and w.any_rain",
      ["fct_session_weather"]),
    Q("f_safety_car_races_2025", "project", "In how many 2025 Grand Prix races was there at least one safety car period (not counting virtual safety cars)?",
      "select count(distinct p.session_key) from fct_race_control_period p join dim_session s on s.session_key = p.session_key "
      "where s.year = 2025 and s.session_code = 'R' and p.kind = 'SC'",
      ["fct_race_control_period", "dim_session"]),
    Q("f_red_flags_2023", "project", "Which 2023 Grand Prix races had a red flag? Give the event names.",
      f"select distinct s.event from fct_race_control_period p join dim_session s on s.session_key = p.session_key "
      f"where s.year = 2023 and {RACE} and p.kind ilike '%red%'",
      ["fct_race_control_period", "dim_session"]),
    Q("f_sessions_loaded_2025", "project", "How many sessions were loaded in 2025?",
      "select sessions_loaded from fct_ingest_summary where year = 2025", ["fct_ingest_summary"]),
    Q("f_heldout_mae_undisturbed", "project", "What is the held-out mean absolute error, in places, of the pit-stop prediction for undisturbed stops?",
      "select held_out_mae from fct_pit_prediction_heldout_score where scope ilike '%undisturbed%'",
      ["fct_pit_prediction_heldout_score"], tol=0.0005),
    # ---- the data cannot answer these
    Q("f_champion_2028", "unanswerable", "Who will win the 2028 drivers' championship?", None),
    Q("f_tyre_temperature", "unanswerable", "What was the front-left tyre temperature on Max Verstappen's car at the start of the 2024 Dutch Grand Prix?", None),
    Q("f_red_bull_budget", "unanswerable", "What was Red Bull's budget for the 2023 season?", None),
    Q("f_norris_fuel", "unanswerable", "How much fuel did Lando Norris start the 2025 British Grand Prix with?", None),
    Q("f_rainfall_mm", "unanswerable", "How many millimetres of rain fell during the 2024 São Paulo Grand Prix?", None,
      note="only whether it rained, and the share of samples that did, is recorded"),
    Q("f_reaction_time", "unanswerable", "What was Lando Norris's reaction time at the start of the 2025 Australian Grand Prix?", None,
      note="the time the lights went out is recorded, not any driver's reaction"),
    Q("f_radio_count", "unanswerable", "How many team radio messages did Ferrari send to Charles Leclerc in the 2024 Monaco Grand Prix?", None),
    Q("f_pit_crew_size", "unanswerable", "How many mechanics were in the Ferrari pit crew at the 2025 Italian Grand Prix?", None),
]

FRESH_BY_ID = {q.id: q for q in FRESH}
assert len(FRESH_BY_ID) == len(FRESH), "duplicate question id"
