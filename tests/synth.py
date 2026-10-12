"""Synthetic session: three cars lapping a circular track at constant speeds."""

import numpy as np
import pandas as pd

R = 10_000                    # circle radius in position units (1/10 m)
LAP_TIMES = {"AAA": 90.0, "BBB": 91.0, "CCC": 95.0}
NUMBERS = {"AAA": 1, "BBB": 2, "CCC": 3}
N_LAPS = 6


def make_session(root, year=2099, rnd=1, code="R"):
    def path(table):
        p = root / table / f"year={year}" / f"round={rnd:02d}" / f"session={code}"
        p.mkdir(parents=True, exist_ok=True)
        return p / "part.parquet"

    rows = []
    for name, lt in LAP_TIMES.items():
        for n in range(1, N_LAPS + 1):
            start, end = (n - 1) * lt, n * lt
            rows.append({
                "Driver": name, "DriverNumber": str(NUMBERS[name]), "Team": "Test",
                "LapNumber": float(n), "LapTime_s": lt,
                "LapStartTime_s": start, "Time_s": end,
                "Sector1Time_s": lt / 3, "Sector2Time_s": lt / 3, "Sector3Time_s": lt / 3,
                "Sector1SessionTime_s": start + lt / 3,
                "Sector2SessionTime_s": start + 2 * lt / 3,
                "Sector3SessionTime_s": end,
                "PitInTime_s": np.nan, "PitOutTime_s": np.nan,
                "Compound": "MEDIUM", "TyreLife": float(n), "Stint": 1.0,
                "TrackStatus": "1", "Position": np.nan})
    laps = pd.DataFrame(rows)
    laps["Position"] = laps.groupby("LapNumber")["Time_s"].rank(method="first")
    laps.to_parquet(path("laps"), index=False)

    pd.DataFrame({
        "Abbreviation": list(NUMBERS), "Position": [1.0, 2.0, 3.0],
        "GridPosition": [1.0, 2.0, 3.0], "Status": ["Finished"] * 3,
    }).to_parquet(path("results"), index=False)

    frames = []
    for name, lt in LAP_TIMES.items():
        t = np.arange(0.0, N_LAPS * lt + 20.0, 0.25)
        theta = 2 * np.pi * ((t / lt) % 1.0)
        frames.append(pd.DataFrame({
            "driver_number": np.full(len(t), NUMBERS[name], dtype="int16"),
            "session_time_s": t.astype("float32"),
            "x": np.round(R * np.cos(theta)).astype("int32"),
            "y": np.round(R * np.sin(theta)).astype("int32")}))
    pd.concat(frames).to_parquet(path("telemetry_pos"), index=False)
