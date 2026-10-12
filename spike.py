import shutil
import sys
import time
from pathlib import Path

import fastf1
import pandas as pd

CACHE = Path("data/cache")
OUT = Path("data/spike")
CACHE.mkdir(parents=True, exist_ok=True)
fastf1.Cache.enable_cache(str(CACHE))


def dir_mb(path: Path) -> float:
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file()) / 1e6


def has(session, attr: str) -> bool:
    try:
        return len(getattr(session, attr)) > 0
    except Exception:
        return False


def main(year: int, event: str, code: str, keep_cache: bool) -> None:
    print(f"fastf1 {fastf1.__version__}")
    t0 = time.monotonic()
    session = fastf1.get_session(year, event, code)
    session.load(laps=True, telemetry=True, weather=True, messages=True)
    print(f"\nloaded {session.event['EventName']} {year} {session.name} "
          f"in {time.monotonic() - t0:.0f}s | raw cache {dir_mb(CACHE):.0f} MB")

    laps = session.laps
    print(f"\nLAPS: {len(laps)} rows, {laps['Driver'].nunique()} drivers")
    for col in ["LapTime", "Sector1Time", "Sector2Time", "Sector3Time",
                "Compound", "TyreLife", "Position", "PitInTime"]:
        if col in laps:
            print(f"  {col:12} populated {100 * laps[col].notna().mean():5.1f}%")

    frames = {"laps": laps}
    if has(session, "weather_data"):
        frames["weather"] = session.weather_data
        print(f"\nWEATHER rows: {len(session.weather_data)}")
    if has(session, "race_control_messages"):
        print(f"RACE CONTROL messages: {len(session.race_control_messages)}")

    if has(session, "car_data") and has(session, "pos_data"):
        car, pos = session.car_data, session.pos_data
        first = next(iter(car))
        step = car[first]["Date"].diff().dt.total_seconds().median()
        print(f"\nTELEMETRY: loaded. {len(car)} drivers; driver {first}: "
              f"{len(car[first])} rows, median step {step:.3f}s")
        frames["car_data"] = pd.concat([d.assign(DriverNumber=n) for n, d in car.items()])
        frames["pos_data"] = pd.concat([d.assign(DriverNumber=n) for n, d in pos.items()])
    else:
        print("\nTELEMETRY: NOT LOADED for this session")

    OUT.mkdir(parents=True, exist_ok=True)
    print("\nPARQUET:")
    for name, df in frames.items():
        try:
            path = OUT / f"{year}_{event}_{code}_{name}.parquet"
            df.to_parquet(path, compression="zstd")
            print(f"  {name:9} {len(df):8d} rows  {path.stat().st_size / 1e6:6.2f} MB")
        except Exception as e:
            print(f"  {name:9} FAILED: {type(e).__name__}: {e}")

    if not keep_cache:
        freed = dir_mb(CACHE)
        shutil.rmtree(CACHE)
        CACHE.mkdir(parents=True, exist_ok=True)
        print(f"\ncache cleared, freed {freed:.0f} MB")


if __name__ == "__main__":
    main(int(sys.argv[1]), sys.argv[2], sys.argv[3], "keep" in sys.argv[4:])
