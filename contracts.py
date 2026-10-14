"""Data contracts for the Parquet lake, checked at ingest time.

Two levels, both written with pandera:
  HARD  structure: required columns present, key columns not null, numeric columns numeric.
        A failure raises ContractError; ingest.py records the table as failed (and it is retried later).
  SOFT  values: plausible ranges and known code sets. A failure never blocks the write; it is returned as a
        finding, which ingest.py stores in the manifest row. A rule only reports when more than its tolerance
        of the rows break it (TOLERANCE), so known glitches in the source do not drown real drift.

Everything here was derived from a profile of the 706 loaded sessions (logs/profile_lake.txt), not guessed.
`event` is added by ingest.py before validation; year/round/session are partition keys and are not validated.
"""
from __future__ import annotations

import pandas as pd

try:
    import pandera.pandas as pa
except ImportError:  # older pandera
    import pandera as pa


class ContractError(Exception):
    """A hard contract failed: the table is structurally wrong."""


def _numeric(s: pd.Series) -> bool:
    # an all-null column (a session with no sector times, say) is stored untyped, so it must pass
    return bool(pd.api.types.is_numeric_dtype(s) or s.isna().all())


def _present(names, nullable=True):
    return {n: pa.Column(required=True, nullable=nullable) for n in names}


def _numeric_cols(names, nullable=True):
    return {n: pa.Column(required=True, nullable=nullable,
                         checks=pa.Check(_numeric, name="is_numeric", error="column is not numeric"))
            for n in names}


# ------------------------------------------------------------------ hard (structure)
_LAPS_TEXT = ["event", "Driver", "DriverNumber", "IsPersonalBest", "Compound", "FreshTyre", "Team",
              "LapStartDate", "TrackStatus", "Deleted", "DeletedReason", "FastF1Generated", "IsAccurate"]
_LAPS_NUM = ["Stint", "SpeedI1", "SpeedI2", "SpeedFL", "SpeedST", "TyreLife", "Position", "LapTime_s",
             "PitOutTime_s", "PitInTime_s", "Sector1Time_s", "Sector2Time_s", "Sector3Time_s",
             "Sector1SessionTime_s", "Sector2SessionTime_s", "Sector3SessionTime_s", "LapStartTime_s"]
_RESULTS_TEXT = ["event", "DriverNumber", "BroadcastName", "Abbreviation", "DriverId", "TeamName", "TeamColor",
                 "TeamId", "FirstName", "LastName", "FullName", "HeadshotUrl", "CountryCode",
                 "ClassifiedPosition", "Status"]
_RESULTS_NUM = ["Position", "GridPosition", "Points", "Laps", "Q1_s", "Q2_s", "Q3_s", "Time_s"]
_WEATHER_NUM = ["AirTemp", "Humidity", "Pressure", "TrackTemp", "WindDirection", "WindSpeed", "Time_s"]
_TEL_CAR = ["speed", "rpm", "ngear", "throttle", "drs"]
_TEL_POS = ["x", "y", "z"]

HARD = {
    "laps": pa.DataFrameSchema({
        **_present(_LAPS_TEXT), **_numeric_cols(_LAPS_NUM),
        "Driver": pa.Column(required=True, nullable=False),
        "LapNumber": pa.Column(required=True, nullable=False,
                               checks=pa.Check(_numeric, name="is_numeric", error="column is not numeric")),
        "Time_s": pa.Column(required=True, nullable=False,
                            checks=pa.Check(_numeric, name="is_numeric", error="column is not numeric")),
    }, strict=False),
    "results": pa.DataFrameSchema({
        **_present(_RESULTS_TEXT), **_numeric_cols(_RESULTS_NUM),
        "Abbreviation": pa.Column(required=True, nullable=False),
    }, strict=False),
    "weather": pa.DataFrameSchema({**_present(["event"]), **_numeric_cols(_WEATHER_NUM)}, strict=False),
    "telemetry_car": pa.DataFrameSchema({
        **_present(["event", "date_utc", "brake"]), **_numeric_cols(_TEL_CAR),
        "driver_number": pa.Column(required=True, nullable=False),
        "session_time_s": pa.Column(required=True, nullable=False),
    }, strict=False),
    "telemetry_pos": pa.DataFrameSchema({
        **_present(["event", "date_utc", "status"]), **_numeric_cols(_TEL_POS),
        "driver_number": pa.Column(required=True, nullable=False),
        "session_time_s": pa.Column(required=True, nullable=False),
    }, strict=False),
    "race_control": pa.DataFrameSchema(
        _present(["event", "Time", "Category", "Message", "Status", "Flag", "Scope", "Sector",
                  "RacingNumber", "Lap"]), strict=False),
    "track_status": pa.DataFrameSchema({
        **_present(["event", "Message"]), "Status": pa.Column(required=True, nullable=False),
        "Time_s": pa.Column(required=True, nullable=False)}, strict=False),
    "session_status": pa.DataFrameSchema({
        "event": pa.Column(required=True), "Status": pa.Column(required=True, nullable=False),
        "Time_s": pa.Column(required=True, nullable=False)}, strict=False),
}


# ------------------------------------------------------------------ soft (values)
def _range(table, col, lo, hi):
    name = f"{table}.{col} in [{lo}, {hi}]"
    return col, pa.Check(lambda s, lo=lo, hi=hi: s.between(lo, hi), name=name)


def _in(table, col, allowed):
    return col, pa.Check(lambda s, a=frozenset(allowed): s.isin(a), name=f"{table}.{col} in known set")


COMPOUNDS = ["SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET", "SUPERSOFT", "ULTRASOFT", "HYPERSOFT",
             "TEST_UNKNOWN", "UNKNOWN", "nan", "None", ""]   # 'nan', 'None' and '' are missing values stored as text
DRS_CODES = [0, 1, 2, 3, 8, 9, 10, 11, 12, 13, 14, 15]       # observed; meanings not yet verified

def _throttle():
    # Measured on the lake: values are 0-100 plus the single code 104 (about 21% of samples, every season).
    # 104 is not a percentage; its meaning is not verified. Nothing is seen at 101-103.
    return "throttle", pa.Check(lambda s: s.between(0, 100) | (s == 104),
                                name="telemetry_car.throttle is 0-100 or the code 104")


_SOFT_RULES = {
    "laps": [_range("laps", "LapTime_s", 30, 3600), _range("laps", "LapNumber", 1, 100),
             _range("laps", "Position", 1, 24), _range("laps", "TyreLife", 0, 100),
             _range("laps", "Stint", 1, 20), _range("laps", "Time_s", -600, 40000),
             _in("laps", "Compound", COMPOUNDS)],
    "results": [_range("results", "Position", 1, 24), _range("results", "GridPosition", 0, 24),
                _range("results", "Points", 0, 30), _range("results", "Laps", 0, 100)],
    "weather": [_range("weather", "AirTemp", -10, 60), _range("weather", "TrackTemp", -10, 90),
                _range("weather", "Humidity", 0, 100), _range("weather", "Pressure", 700, 1100),
                _range("weather", "WindSpeed", 0, 40), _range("weather", "WindDirection", -360, 360)],
    "telemetry_car": [_range("telemetry_car", "speed", 0, 400), _range("telemetry_car", "rpm", 0, 20000),
                      _range("telemetry_car", "ngear", 0, 8), _throttle(),
                      _in("telemetry_car", "drs", DRS_CODES)],
    "telemetry_pos": [_range("telemetry_pos", "x", -50000, 50000), _range("telemetry_pos", "y", -50000, 50000),
                      _in("telemetry_pos", "status", ["OnTrack", "OffTrack"])],
    "race_control": [_in("race_control", "Category", ["Flag", "Other", "CarEvent", "Drs", "SafetyCar"]),
                     _in("race_control", "Flag", ["BLUE", "CLEAR", "YELLOW", "DOUBLE YELLOW", "GREEN",
                                                  "CHEQUERED", "RED", "BLACK AND WHITE"]),
                     _in("race_control", "Scope", ["Sector", "Driver", "Track"])],
    "track_status": [_in("track_status", "Status", ["1", "2", "4", "5", "6", "7"])],
    "session_status": [_in("session_status", "Status",
                           ["Started", "Inactive", "Finished", "Ends", "Finalised", "Aborted"])],
}

# whole-frame rules
_LAP_UNIQUE = pa.Check(lambda df: ~df.duplicated(["Driver", "LapNumber"], keep=False),
                       name="laps.(Driver, LapNumber) is unique")
_RESULT_CLASS = pa.Check(lambda s: s.astype(str).str.fullmatch(r"\d{1,2}|[A-Z]|"),
                         name="results.ClassifiedPosition is a number or one letter")

SOFT = {}
for _t, _rules in _SOFT_RULES.items():
    _cols = {c: pa.Column(required=False, nullable=True, checks=[ck]) for c, ck in _rules}
    if _t == "results":
        _cols["ClassifiedPosition"] = pa.Column(required=False, nullable=True, checks=[_RESULT_CLASS])
    SOFT[_t] = pa.DataFrameSchema(_cols, checks=[_LAP_UNIQUE] if _t == "laps" else [], strict=False)

# share of rows allowed to break a rule before it is reported (default 0). Set from the lake-wide check.
TOLERANCE: dict[str, float] = {
    # gear values above 8 (9 to 20+) appear in about 0.1% of rows in 96 of 269 sessions, worst 0.17%
    "telemetry_car.ngear in [0, 8]": 0.005,
}


def _summarise(exc) -> pd.DataFrame:
    """One row per rule with the number of rows that break it (a frame-level rule is reported once per column)."""
    fc = exc.failure_cases
    per = fc.groupby(["check", fc["column"].astype(str)]).size().reset_index(name="bad_rows")
    return per.groupby("check", as_index=False)["bad_rows"].max()


def validate(table: str, df: pd.DataFrame) -> list[dict]:
    """Raise ContractError on a hard failure; otherwise return the soft findings (possibly empty)."""
    if table in HARD:
        try:
            HARD[table].validate(df, lazy=True)
        except pa.errors.SchemaErrors as e:
            fc = e.failure_cases
            first = fc[["column", "check", "failure_case"]].astype(str).drop_duplicates().head(6).to_dict("records")
            raise ContractError(f"{table}: {len(fc)} structural failures, e.g. {first}") from None
    findings = []
    if table in SOFT and len(df):
        try:
            SOFT[table].validate(df, lazy=True)
        except pa.errors.SchemaErrors as e:
            for r in _summarise(e).itertuples():
                share = r.bad_rows / len(df)
                if share > TOLERANCE.get(str(r.check), 0.0):
                    findings.append({"rule": str(r.check), "bad_rows": int(r.bad_rows),
                                     "share": round(share, 6)})
    return findings
