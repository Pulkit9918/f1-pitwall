"""The evaluation set: questions with reference SQL, written by hand, and questions the data cannot answer.

Each question has
  id         short stable name
  category   lookup, aggregate, join, project (the project's own models), history, data-gap or unanswerable
  question   what the agent is asked, including the form of the answer
  sql        reference SQL (None for an unanswerable question); the expected answer is computed from it at run time,
             so it stays right when the data is refreshed, and is never produced by the model being tested
  tables     the gold tables a correct query needs (used to score table routing)
  ordered    True when the row order is part of the answer
  tol        tolerance for decimal values (default 0.01)

An unanswerable question has sql=None. The right behaviour is to say so and not to run a query that returns a number.
"""
from dataclasses import dataclass, field

RACE = "s.session_code = 'R'"
J_RES = "from fct_result r join dim_session s on s.session_key = r.session_key"


@dataclass(frozen=True)
class Question:
    id: str
    category: str
    question: str
    sql: str | None
    tables: tuple[str, ...] = ()
    ordered: bool = False
    tol: float = 0.01
    note: str = ""

    @property
    def answerable(self) -> bool:
        return self.sql is not None


def Q(id, category, question, sql, tables=(), ordered=False, tol=0.01, note=""):
    return Question(id, category, question, " ".join(sql.split()) if sql else None, tuple(tables), ordered, tol, note)


QUESTIONS: list[Question] = [
    # ---- lookups
    Q("winner_2025_italy", "lookup", "Which driver won the 2025 Italian Grand Prix? Give the three-letter driver code.",
      f"select r.driver_code {J_RES} where s.year = 2025 and {RACE} and s.event ilike '%Italian%' and r.position = 1",
      ["fct_result", "dim_session"]),
    Q("pole_2025_monaco", "lookup", "Who took pole position for the 2025 Monaco Grand Prix? Give the three-letter driver code.",
      f"select r.driver_code {J_RES} where s.year = 2025 and s.session_code = 'Q' and s.event ilike '%Monaco%' and r.position = 1",
      ["fct_result", "dim_session"]),
    Q("round_2025_singapore", "lookup", "In which round of 2025 was the Singapore Grand Prix run? Give the round number.",
      f"select s.round from dim_session s where s.year = 2025 and {RACE} and s.event ilike '%Singapore%'",
      ["dim_session"]),
    Q("circuit_2024_belgium", "lookup", "On which circuit was the 2024 Belgian Grand Prix run? Give the circuit name.",
      f"select s.circuit_name from dim_session_circuit s where s.year = 2024 and {RACE} and s.event ilike '%Belgian%'",
      ["dim_session_circuit"]),
    Q("grid_2024_sao_paulo", "lookup", "Where did Max Verstappen start the 2024 São Paulo Grand Prix? Give the grid position.",
      "select grid from fct_season_result where season = 2024 and driver_id = 'max_verstappen' "
      "and (race_name ilike '%Paulo%' or race_name ilike '%Brazil%')",
      ["fct_season_result"]),
    Q("team_2024_sainz", "lookup", "Which team did Carlos Sainz drive for in the 2024 Australian Grand Prix? Give the team name.",
      f"select r.team_name {J_RES} where s.year = 2024 and {RACE} and s.event ilike '%Australian%' and r.driver_code = 'SAI'",
      ["fct_result", "dim_session"]),
    Q("laps_2025_norris_britain", "lookup", "How many laps did Lando Norris complete in the 2025 British Grand Prix race?",
      f"select r.laps_completed {J_RES} where s.year = 2025 and {RACE} and s.event ilike '%British%' and r.driver_code = 'NOR'",
      ["fct_result", "dim_session"]),
    Q("front_row_2025_hungary", "lookup", "Which drivers started on the front row (grid positions 1 and 2) of the 2025 Hungarian Grand Prix? Give the three-letter driver codes.",
      f"select r.driver_code {J_RES} where s.year = 2025 and {RACE} and s.event ilike '%Hungarian%' and r.grid_position in (1, 2)",
      ["fct_result", "dim_session"]),
    # ---- aggregates
    Q("hamilton_wins_2007_2024", "aggregate", "How many Grands Prix did Lewis Hamilton win from 2007 to 2024 inclusive?",
      "select count(*) from fct_season_result where driver_id = 'hamilton' and is_win and season between 2007 and 2024",
      ["fct_season_result"]),
    Q("races_2021", "aggregate", "How many races were run in the 2021 season?",
      "select count(distinct round) from fct_season_result where season = 2021", ["fct_season_result"]),
    Q("winners_2021", "aggregate", "How many different drivers won a Grand Prix in 2021?",
      "select count(distinct driver_id) from fct_season_result where season = 2021 and is_win", ["fct_season_result"]),
    Q("leclerc_podiums_2022", "aggregate", "How many podium finishes did Charles Leclerc have in 2022?",
      "select count(*) from fct_season_result where season = 2022 and driver_id = 'leclerc' and is_podium",
      ["fct_season_result"]),
    Q("constructor_champion_2022", "aggregate", "Which constructor won the 2022 constructors' championship? Give the constructor id.",
      "select constructor_id from fct_constructor_standing where season = 2022 and "
      "round = (select max(round) from fct_constructor_standing where season = 2022) and position = 1",
      ["fct_constructor_standing"]),
    Q("driver_champion_2023", "aggregate", "Which driver won the 2023 drivers' championship? Give the driver id.",
      "select driver_id from fct_driver_standing where season = 2023 and "
      "round = (select max(round) from fct_driver_standing where season = 2023) and position = 1",
      ["fct_driver_standing"]),
    Q("most_monaco_wins", "aggregate", "Which driver has won the most Monaco Grands Prix? Give the driver id.",
      "select driver_id from fct_season_result where circuit_id = 'monaco' and is_win "
      "group by driver_id order by count(*) desc, driver_id limit 1",
      ["fct_season_result"], note="check_reference prints the top three so a tie can be spotted"),
    # ---- joins and laps
    Q("fastest_lap_2025_abu_dhabi", "join", "Who set the fastest race lap of the 2025 Abu Dhabi Grand Prix, and what was the time in seconds? Ignore deleted laps.",
      f"select l.driver_code, l.lap_time_s from fct_lap l join dim_session s on s.session_key = l.session_key "
      f"where s.year = 2025 and {RACE} and s.event ilike '%Abu Dhabi%' and not coalesce(l.deleted, false) "
      f"and l.lap_time_s is not null order by l.lap_time_s limit 1",
      ["fct_lap", "dim_session"], tol=0.001),
    Q("race_laps_2025_singapore", "join", "How many laps long was the 2025 Singapore Grand Prix race?",
      f"select max(l.lap_number) from fct_lap l join dim_session s on s.session_key = l.session_key "
      f"where s.year = 2025 and {RACE} and s.event ilike '%Singapore%'",
      ["fct_lap", "dim_session"]),
    Q("leader_lap20_2025_dutch", "join", "Who led the 2025 Dutch Grand Prix race at the end of lap 20? Give the three-letter driver code.",
      f"select g.driver_code from fct_lap_gap g join dim_session s on s.session_key = g.session_key "
      f"where s.year = 2025 and {RACE} and s.event ilike '%Dutch%' and g.lap_number = 20 and g.position = 1",
      ["fct_lap_gap", "dim_session"]),
    Q("purple_ver_2025_italy_q", "join", "How many purple sectors did Max Verstappen set in 2025 Italian Grand Prix qualifying?",
      "select count(*) from fct_lap_sector x join dim_session s on s.session_key = x.session_key "
      "where s.year = 2025 and s.session_code = 'Q' and s.event ilike '%Italian%' and x.driver_code = 'VER' and x.status = 'purple'",
      ["fct_lap_sector", "dim_session"]),
    Q("compound_2025_spain", "join", "Which tyre compound was used in the most stints in the 2025 Spanish Grand Prix race? Give the compound and the number of stints.",
      f"select f.compound, count(*) from fct_stint f join dim_session s on s.session_key = f.session_key "
      f"where s.year = 2025 and {RACE} and s.event ilike '%Spanish%' group by f.compound order by count(*) desc, f.compound limit 1",
      ["fct_stint", "dim_session"], note="check_reference prints the top three so a tie can be spotted"),
    Q("russell_stops_2024_hungary", "join", "How many pit stops did George Russell make in the 2024 Hungarian Grand Prix race?",
      f"select count(*) from fct_pit_stop p join dim_session s on s.session_key = p.session_key "
      f"where s.year = 2024 and {RACE} and s.event ilike '%Hungarian%' and p.driver_code = 'RUS' and p.is_race_session",
      ["fct_pit_stop", "dim_session"]),
    # ---- the project's own models
    Q("highest_pit_loss_circuit", "project", "Which circuit has the highest median green-flag pit loss, counting only circuits marked reliable? Give the circuit name.",
      "select circuit_name from fct_circuit_pit_loss where is_reliable order by median_pit_loss_s desc limit 1",
      ["fct_circuit_pit_loss"]),
    Q("spa_pit_loss", "project", "What is the median green-flag pit loss at Spa, in seconds?",
      "select median_pit_loss_s from fct_circuit_pit_loss where circuit_name ilike '%Spa%'", ["fct_circuit_pit_loss"]),
    Q("long_pit_losses", "project", "How many measured green-flag pit stops lost more than 30 seconds?",
      "select count(*) from fct_pit_loss where pit_loss_s > 30", ["fct_pit_loss"]),
    Q("degradation_bahrain", "project", "At Bahrain, which tyre compound has the highest median degradation per lap, counting only reliable rows? Give the compound.",
      "select compound from fct_circuit_degradation where circuit_name ilike '%Bahrain%' and is_reliable "
      "order by median_degradation_s_per_lap desc limit 1",
      ["fct_circuit_degradation"]),
    Q("hottest_race_2025", "project", "Which 2025 Grand Prix race had the highest average track temperature? Give the event name.",
      f"select s.event from fct_session_weather w join dim_session s on s.session_key = w.session_key "
      f"where s.year = 2025 and {RACE} order by w.avg_track_temp desc limit 1",
      ["fct_session_weather", "dim_session"]),
    Q("rain_races_2024", "project", "In how many 2024 Grand Prix races did it rain at some point?",
      "select count(*) from fct_session_weather w where w.year = 2024 and w.session_code = 'R' and w.any_rain",
      ["fct_session_weather"]),
    Q("safety_car_races_2024", "project", "In how many 2024 Grand Prix races was there at least one safety car period (not counting virtual safety cars)?",
      "select count(distinct p.session_key) from fct_race_control_period p join dim_session s on s.session_key = p.session_key "
      "where s.year = 2024 and s.session_code = 'R' and p.kind = 'SC'",
      ["fct_race_control_period", "dim_session"]),
    Q("red_flags_2024", "project", "Which 2024 Grand Prix races had a red flag? Give the event names.",
      f"select distinct s.event from fct_race_control_period p join dim_session s on s.session_key = p.session_key "
      f"where s.year = 2024 and {RACE} and p.kind ilike '%red%'",
      ["fct_race_control_period", "dim_session"]),
    Q("heldout_hit_rate_undisturbed", "project", "What is the held-out exact-position hit rate of the pit-stop prediction for undisturbed stops? Give it as a fraction between 0 and 1.",
      "select held_out_hit_rate from fct_pit_prediction_heldout_score where scope ilike '%undisturbed%'",
      ["fct_pit_prediction_heldout_score"], tol=0.0005),
    Q("prediction_checks_2025", "project", "How many pit stops from 2025 are in the pit-stop prediction check table?",
      "select count(*) from fct_pit_prediction_check where year = 2025", ["fct_pit_prediction_check"]),
    Q("sessions_loaded_per_year", "project", "For each year from 2022 to 2024, how many sessions were loaded? Give the year and the count, in year order.",
      "select year, sessions_loaded from fct_ingest_summary where year between 2022 and 2024 order by year",
      ["fct_ingest_summary"], ordered=True),
    # ---- history
    Q("champion_1988", "history", "Who won the 1988 drivers' championship? Give the driver id.",
      "select driver_id from fct_driver_standing where season = 1988 and "
      "round = (select max(round) from fct_driver_standing where season = 1988) and position = 1",
      ["fct_driver_standing"]),
    # ---- answerable although the data has a known gap (laps are missing for this race, results are not)
    Q("winner_2018_italy", "data-gap", "Who won the 2018 Italian Grand Prix? Give the three-letter driver code.",
      f"select r.driver_code {J_RES} where s.year = 2018 and {RACE} and s.event ilike '%Italian%' and r.position = 1",
      ["fct_result", "dim_session"], note="the lake has results but no laps for this race; a good agent does not refuse"),
    # ---- the data cannot answer these
    Q("next_race_winner", "unanswerable", "Who will win the next Formula 1 race?", None),
    Q("champion_2027", "unanswerable", "Who will win the 2027 drivers' championship?", None),
    Q("tyre_pressures", "unanswerable", "What tyre pressures did McLaren run in the 2025 Dutch Grand Prix?", None),
    Q("verstappen_salary", "unanswerable", "How much money did Max Verstappen earn in 2024?", None),
    Q("engine_mode", "unanswerable", "Which engine mode did Lewis Hamilton use on lap 10 of the 2024 British Grand Prix?", None),
    Q("stationary_time", "unanswerable", "What was Lando Norris's stationary pit stop time in the 2025 Spanish Grand Prix?", None,
      note="only the time in the pit lane is recorded, not the time the car stood still"),
    Q("wind_direction", "unanswerable", "What was the wind direction during the 2025 Singapore Grand Prix?", None,
      note="wind speed is recorded, direction is not"),
    Q("attendance", "unanswerable", "How many fans attended the 2025 British Grand Prix?", None),
    Q("fastest_lap_1998_monaco", "unanswerable", "What was the fastest lap time at the 1998 Monaco Grand Prix?", None,
      note="lap times start in 2018; older races have results only"),
    Q("turn1_speed_2025_bahrain", "unanswerable", "Which driver was fastest through Turn 1 in the 2025 Bahrain Grand Prix?", None,
      note="there is no corner-level data in the gold tables"),
]

BY_ID = {q.id: q for q in QUESTIONS}
assert len(BY_ID) == len(QUESTIONS), "duplicate question id"
