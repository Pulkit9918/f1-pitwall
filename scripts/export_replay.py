"""Export race and qualifying replays as static JSON files for the web front end.

usage (repository root):
    python scripts/export_replay.py [--db data/f1_dbt.duckdb] [--lake data/lake] [--out web/public/replay-data]
                                    [--from-year 2022] [--sessions R,Q] [--only 2026-R06-R ...] [--force]

For every session that has position telemetry it writes  <session_key>.json  and, at the end,  index.json.
Each replay holds, sampled once a second:
  * where each car is, as distance along one lap of the circuit (so the page can draw it on an outline),
  * speed, gear, throttle, brake and the raw DRS code,
  * the weather, the race-control messages and the track-status changes, all on the session clock,
  * the circuit outline, taken from the fastest clean lap of that session.
Cars are placed by snapping each x/y sample to that outline. Progress is unwrapped lap after lap, so a car 1.4 laps in
sits at 1.4. For race sessions the script then compares each car's progress at the end of its last lap with the lap
count in the gold table and prints how many cars agree to within 0.2 of a lap. That is the only check on the snapping.

Sessions already written are skipped unless --force is given. The output folder is only touched if it is empty or was
written by this script (it holds an index.json from it); any other folder is refused and left alone. It is separate
from web/public/data, because scripts/export_static.py wipes that folder on every run.
"""
import argparse
import glob
import gzip
import json
import math
import re
import sys
import time
from pathlib import Path

import duckdb

try:
    import numpy as np
except ImportError:  # pragma: no cover
    sys.exit("numpy is required: pip install numpy")

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "f1_dbt.duckdb"
DEFAULT_LAKE = ROOT / "data" / "lake"
DEFAULT_OUT = ROOT / "web" / "public" / "replay-data"

GENERATOR = "export_replay"
SCHEMA = 1
STEP_S = 1.0          # seconds between samples
REF_POINTS = 1000     # resolution of the circuit line used for snapping
DRAW_POINTS = 500     # points of the outline sent to the page
VIEW = 1000.0         # the outline is scaled to fit a box this big
BACK_WINDOW = 20      # when snapping, how far back (in reference points) a car may move between samples
FWD_WINDOW = 150      # ... and how far forward (15% of a lap)
HOLE_S = 3.0          # position samples further apart than this are a hole in the data, not a slow stretch
BACK_LIMIT = 0.03     # a step back of more than this (fraction of a lap) is not a car going backwards, it is a bad sample
MAX_HOLD = 30         # ... and is ignored for at most this many samples in a row before the car is taken to be there
RACE_LIKE = {"R", "S"}
MIN_COVERAGE = 0.5    # a session whose valid position data covers less of its lap window than this is not exported


# ---------------------------------------------------------------- lake lookups

def norm(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


def lake_files(lake, table):
    return sorted(glob.glob(f"{lake}/{table}/**/*.parquet", recursive=True))


PATH_KEY = re.compile(r"year=(\d+)[/\\]round=(\d+)[/\\]session=([^/\\]+)")


def file_index(con, lake, table):
    """{(year, round, session): [parquet files]}, read from the folder names year=Y/round=R/session=S."""
    out = {}
    for f in lake_files(lake, table):
        m = PATH_KEY.search(f)
        if m:
            out.setdefault((int(m.group(1)), int(m.group(2)), m.group(3)), []).append(f)
    return out


def driver_numbers(con, lake):
    """{(year, round, session): {driver number: three-letter code}} from the lake's results (or laps) table."""
    tried = []
    for table, code_names in (("results", ("abbreviation", "driver", "drivercode", "code")),
                              ("laps", ("driver", "drivercode", "abbreviation", "code"))):
        files = lake_files(lake, table)
        if not files:
            tried.append(f"{table}: no files")
            continue
        cols = {norm(r[0]): r[0] for r in con.execute("describe select * from read_parquet(?, union_by_name=true, "
                                                       "hive_partitioning=false)", [files]).fetchall()}
        num = next((cols[n] for n in ("drivernumber", "racingnumber", "number") if n in cols), None)
        code = next((cols[n] for n in code_names if n in cols), None)
        if not (num and code):
            tried.append(f"{table}: columns are {sorted(cols.values())}")
            continue
        rows = con.execute(
            f'select distinct filename, try_cast("{num}" as integer), cast("{code}" as varchar) '
            f"from read_parquet(?, union_by_name=true, filename=true, hive_partitioning=false)", [files]).fetchall()
        out = {}
        for f, n, c in rows:
            m = PATH_KEY.search(f)
            if m and n is not None and c:
                out.setdefault((int(m.group(1)), int(m.group(2)), m.group(3)), {})[int(n)] = c
        if out:
            return out
        tried.append(f"{table}: no usable rows")
    sys.exit("REFUSING: cannot map car numbers to driver codes. " + "; ".join(tried))


HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")


def driver_teams(con, files):
    """{driver code: [team name, "#RRGGBB" or None]} from a results file; {} if it has no team columns."""
    if not files:
        return {}
    cols = {norm(r[0]): r[0] for r in con.execute(
        "describe select * from read_parquet(?, hive_partitioning=false)", [files[0]]).fetchall()}
    if "abbreviation" not in cols or not ({"teamname", "teamcolor"} & set(cols)):
        return {}
    name = f'cast("{cols["teamname"]}" as varchar)' if "teamname" in cols else "null"
    color = f'cast("{cols["teamcolor"]}" as varchar)' if "teamcolor" in cols else "null"
    out = {}
    for code, n, c in con.execute(
            f'select cast("{cols["abbreviation"]}" as varchar), {name}, {color} from read_parquet(?, '
            f"hive_partitioning=false)", [files[0]]).fetchall():
        m = HEX.match((c or "").strip())
        if code:
            out[code] = [n or None, "#" + m.group(1).upper() if m else None]
    return out


# ---------------------------------------------------------------- the circuit line and snapping

def split_by_driver(driver_col):
    """Slices of a sorted driver-number column: {number: (start, stop)}."""
    out = {}
    nums, starts = np.unique(driver_col, return_index=True)
    stops = list(starts[1:]) + [len(driver_col)]
    for n, a, b in zip(nums, starts, stops):
        out[int(n)] = (int(a), int(b))
    return out


def reference_line(t, x, y, t0, t1):
    """The circuit as REF_POINTS points evenly spaced along one lap, starting at the lap start. None if too little data."""
    m = (t >= t0) & (t <= t1)
    px, py = x[m], y[m]
    if len(px) < 30:
        return None
    seg = np.hypot(np.diff(px), np.diff(py))
    d = np.concatenate([[0.0], np.cumsum(seg)])
    if d[-1] <= 0:
        return None
    grid = np.linspace(0.0, d[-1], REF_POINTS, endpoint=False)
    return np.column_stack([np.interp(grid, d, px), np.interp(grid, d, py)])


def snap(points, ref, race_like=True):
    """Distance along the lap, unwrapped (lap 1.4 is 1.4), for each point (an (m, 2) array), against the (N, 2) line.

    A car is matched to the nearest line point that is reachable from where it was a sample ago, so a track that
    crosses itself (Suzuka) does not make cars jump between the two crossings. If no reachable point is close, the
    nearest point anywhere is used instead.

    Cars do not go backwards: a step back of more than BACK_LIMIT of a lap is a bad sample and is ignored (for at most
    MAX_HOLD samples in a row)."""
    n = len(ref)
    diag = float(np.hypot(*(ref.max(0) - ref.min(0))))
    tol = 0.015 * diag
    m = len(points)
    cum = np.empty(m)
    offs = np.arange(-BACK_WINDOW, FWD_WINDOW + 1)
    prev = None
    c = 0.0
    held = 0
    for lo in range(0, m, 512):
        chunk = points[lo:lo + 512]
        d2 = ((chunk[:, None, :] - ref[None, :, :]) ** 2).sum(2)
        gidx = d2.argmin(1)
        gd = np.sqrt(d2[np.arange(len(chunk)), gidx])
        for k in range(len(chunk)):
            if prev is None:
                idx = int(gidx[k])
                c = idx / n
                if c > 0.5:          # on the grid, just before the start line
                    c -= 1.0
            else:
                cand = (prev + offs) % n
                row = d2[k, cand]
                j = int(row.argmin())
                idx = int(cand[j]) if math.sqrt(row[j]) - gd[k] <= tol else int(gidx[k])
                delta = idx / n - (c % 1.0)
                delta -= round(delta)
                if delta < -BACK_LIMIT and held < MAX_HOLD:
                    held += 1
                    cum[lo + k] = c
                    continue
                held = 0
                c += delta
            prev = idx
            cum[lo + k] = c
    return cum


# ---------------------------------------------------------------- one session

def correct_slips(grid, cum, start, ends, last_t):
    """Fix whole-lap slips in cum (progress, edited in place) against the lap table; returns the number fixed.

    ends is [(lap_number, time the lap ended)]: at that moment progress must be the lap number. Where it is a whole number
    of laps out (and close to it, so a car stopped part way round a lap is left alone), the laps are added or taken away
    at the biggest step in the wrong direction since the last lap end that agreed. A whole lap does not move a car on the
    map; it only puts the lap count, and so the order and gaps, right."""
    fixed = 0
    prev_t = start if start is not None else float(grid[0])
    for lap, te in sorted(ends):
        if te > last_t or te < grid[0] or te > grid[-1] or te <= prev_t:
            continue
        off = float(np.interp(te, grid, cum)) - lap
        k = int(round(off))
        if abs(off - k) > 0.4:
            continue
        if k:
            a = int(np.searchsorted(grid, prev_t))
            b = int(np.searchsorted(grid, te))
            if b > a:
                step = np.diff(cum[a:b + 1])
                j = int(step.argmin() if k < 0 else step.argmax())
                cum[a + j + 1:] -= k
                fixed += 1
        prev_t = te
    return fixed


def clock_offset(epoch_s, t):
    """Seconds to subtract from a wall-clock epoch to get session time (median over the position samples)."""
    ok = np.isfinite(epoch_s)
    if not ok.any():
        return None
    return float(np.median(epoch_s[ok] - t[ok]))


def sample_hold(t_src, v_src, grid):
    """Most recent value at or before each grid time."""
    idx = np.clip(np.searchsorted(t_src, grid, side="right") - 1, 0, len(t_src) - 1)
    return v_src[idx]


def build_replay(con, key, code, pos_file, car_file, weather_file, rc_file, ts_file, numbers, laps_info, lap_ref,
                 teams=None, lap_ends=None):
    """The replay dict for one session, plus a list of notes for the console."""
    notes = []
    p = con.execute(
        "select driver_number, session_time_s, x, y, coalesce(epoch(date_utc), 'nan'::double) from read_parquet(?) "
        "where x is not null and y is not null and session_time_s is not null and not (x = 0 and y = 0) "
        "order by driver_number, session_time_s", [pos_file]).fetchnumpy()
    names = list(p)
    drv, t, x, y, ep = (np.asarray(p[k]) for k in names)
    t = t.astype(float)
    x = x.astype(float)
    y = y.astype(float)
    if len(t) == 0:
        return None, ["no position samples"]
    slices = split_by_driver(drv)

    # the circuit line: the fastest clean lap whose driver has position samples across all of it (lap_ref is a list of
    # candidate laps, fastest first; samples can be missing for a driver, or the data can stop early)
    ref = None
    for ref_code, ref_start, ref_time in (lap_ref or []):
        ref_num = next((n for n, c in numbers.items() if c == ref_code), None)
        if ref_num not in slices:
            continue
        a, b = slices[ref_num]
        tt = t[a:b]
        inside = tt[(tt >= ref_start) & (tt <= ref_start + ref_time)]
        if len(inside) < 30 or inside[0] - ref_start > 0.1 * ref_time or ref_start + ref_time - inside[-1] > 0.1 * ref_time:
            continue
        ref = reference_line(tt, x[a:b], y[a:b], ref_start, ref_start + ref_time)
        if ref is not None:
            break
    if ref is None:
        return None, ["no lap had position samples across all of it to draw the circuit from"]

    lo = float(min(t[a] for a, _ in slices.values()))
    hi = float(max(t[b - 1] for _, b in slices.values()))
    grid = np.arange(math.ceil(lo), math.floor(hi) + 1, STEP_S)
    n = len(grid)
    race_like = code in RACE_LIKE

    car = None
    if car_file:
        c = con.execute(
            "select driver_number, session_time_s, coalesce(speed, 0), coalesce(ngear, 0), coalesce(throttle, 0), "
            "coalesce(drs, 0), coalesce(cast(brake as integer), 0) from read_parquet(?) where session_time_s is not null "
            "order by driver_number, session_time_s", [car_file]).fetchnumpy()
        cn = [np.asarray(c[k]) for k in c]
        car = (cn, split_by_driver(cn[0]))

    drivers = {}
    final_cum = {}
    slips = 0
    for num, (a, b) in sorted(slices.items()):
        if b - a < 10:
            continue
        ts, xs, ys = t[a:b], x[a:b], y[a:b]
        va = int(np.searchsorted(grid, ts[0], side="left"))
        vb = int(np.searchsorted(grid, ts[-1], side="right")) - 1
        if vb <= va:
            continue
        gt = grid[va:vb + 1]
        # A grid point more than HOLE_S from any real sample is not snapped (a straight line across a hole cuts across
        # the circuit); its progress is filled in from the points either side.
        j = np.clip(np.searchsorted(ts, gt), 1, len(ts) - 1)
        seen = np.minimum(np.abs(gt - ts[j - 1]), np.abs(ts[j] - gt)) <= HOLE_S
        if not seen.any():
            continue
        pts = np.column_stack([np.interp(gt, ts, xs), np.interp(gt, ts, ys)])
        cum = np.full(n, np.nan)
        cum[va:vb + 1] = np.interp(gt, gt[seen], snap(pts[seen], ref, race_like))
        cum[:va] = cum[va]
        cum[vb + 1:] = cum[vb]
        # Progress counts every pass of the line since the car's first sample, including the out lap, the formation lap
        # and the drive to the grid, a different number for each car. Re-zero it at the start of lap 1, where a car on
        # the grid sits just behind the line (progress slightly below zero).
        lap1 = (laps_info.get(numbers.get(num)) or (None, None, None))[2] if race_like else None
        if lap1 is not None and grid[va] <= lap1 <= grid[vb]:
            cum -= float(np.round(np.interp(lap1, grid, cum)))
        drv_code = numbers.get(num, f"#{num}")
        before = cum.copy()
        if race_like and lap_ends and drv_code in lap_ends:
            slips += correct_slips(grid, cum, lap1 if lap1 is not None and grid[va] <= lap1 <= grid[vb] else None,
                                   lap_ends[drv_code], float(ts[-1]))
        q = np.round(cum * 10000).astype(np.int64)
        entry = {"num": num, "a": va, "b": vb, "p0": int(q[0]), "dp": np.diff(q).tolist()}
        if car and num in car[1]:
            cn, cs = car
            ca, cb = cs[num]
            tt = cn[1][ca:cb].astype(float)
            entry["spd"] = sample_hold(tt, cn[2][ca:cb], grid).astype(int).tolist()
            entry["gear"] = sample_hold(tt, cn[3][ca:cb], grid).astype(int).tolist()
            entry["thr"] = np.clip(sample_hold(tt, cn[4][ca:cb], grid), 0, 100).astype(int).tolist()
            entry["drs"] = sample_hold(tt, cn[5][ca:cb], grid).astype(int).tolist()
            entry["brk"] = sample_hold(tt, cn[6][ca:cb], grid).astype(int).tolist()
        drivers[drv_code] = entry
        final_cum[drv_code] = (grid, before, float(ts[-1]), cum)
    if not drivers:
        return None, ["no driver had enough samples"]

    # outline, scaled into a VIEW x VIEW box with y pointing down
    mn, mx = ref.min(0), ref.max(0)
    scale = VIEW / max(float(mx[0] - mn[0]), float(mx[1] - mn[1]))
    sx = (ref[:, 0] - mn[0]) * scale
    sy = (mx[1] - ref[:, 1]) * scale
    step = max(1, REF_POINTS // DRAW_POINTS)
    outline = [[round(float(a), 1), round(float(b), 1)] for a, b in zip(sx[::step], sy[::step])]

    # race-control messages and weather, on the session clock
    off = clock_offset(ep, t)
    messages = []
    if rc_file and off is not None:
        rows = con.execute(
            'select epoch(cast("Time" as timestamp)), "Category", "Flag", "Lap", "Message", "RacingNumber" '
            "from read_parquet(?) order by 1", [rc_file]).fetchall()
        for et, cat, flag, lap, msg, rn in rows:
            if et is None or not msg:
                continue
            st = et - off
            if st < lo - 600 or st > hi + 600:
                continue
            who = numbers.get(int(rn)) if rn and str(rn).strip().isdigit() else None
            messages.append([round(st, 1), cat or "", flag or "", int(lap) if lap is not None else None, msg, who])
    weather = None
    if weather_file:
        rows = con.execute(
            'select "Time_s", "AirTemp", "TrackTemp", "Humidity", cast("Rainfall" as integer), "WindSpeed", '
            '"WindDirection" from read_parquet(?) where "Time_s" is not null order by 1', [weather_file]).fetchall()

        def r1(v):
            return None if v is None or (isinstance(v, float) and not math.isfinite(v)) else round(float(v), 1)

        if rows:
            weather = {"t": [r1(r[0]) for r in rows], "air": [r1(r[1]) for r in rows], "track": [r1(r[2]) for r in rows],
                       "humidity": [r1(r[3]) for r in rows], "rain": [r[4] for r in rows],
                       "wind": [r1(r[5]) for r in rows], "wind_dir": [r[6] for r in rows]}
    status = []
    if ts_file:
        status = [[round(float(a), 1), str(s), str(m or "")] for a, s, m in con.execute(
            'select "Time_s", "Status", "Message" from read_parquet(?) where "Time_s" is not null order by 1',
            [ts_file]).fetchall()]

    # the one check: progress at the end of each car's last lap against the lap count in the gold table
    if race_like:
        def agreement(which):
            good = bad = 0
            for drv_code, (lap_count, lap_end, _lap1, last_time) in laps_info.items():
                if drv_code not in final_cum or lap_end is None:
                    continue
                g, last_t, cm = final_cum[drv_code][0], final_cum[drv_code][2], final_cum[drv_code][which]
                if lap_end > last_t:
                    continue
                i = int(np.searchsorted(g, lap_end))
                if i >= len(g) or not np.isfinite(cm[i]):
                    continue
                # a car that never finished its last lap (a retirement) is somewhere inside it
                # (or has finished it and kept driving: the lap table has no time for it either way)
                lo_ok = lap_count - 1.2 if last_time is None else lap_count - 0.2
                hi_ok = lap_count + 1.2 if last_time is None else lap_count + 0.2
                if lo_ok <= cm[i] <= hi_ok:
                    good += 1
                else:
                    bad += 1
            return good, bad

        # judged on progress as the positions give it, before whole-lap slips are corrected: if most cars are wrong the
        # position data cannot be trusted (it can stop matching the cars' clock part way through a race)
        good, bad = agreement(1)
        if good + bad >= 4 and good < 0.5 * (good + bad):
            return None, [f"position data does not match the lap table (progress agrees for only {good} of "
                          f"{good + bad} cars), so no replay is made"]
        good, bad = agreement(3)
        if good + bad:
            notes.append(f"progress agrees with the lap count for {good} of {good + bad} cars")
        if slips:
            notes.append(f"{slips} whole-lap slips corrected against the lap table")

    return {
        "schema": SCHEMA, "key": key, "kind": "race" if race_like else "quali", "t0": float(grid[0]), "step": STEP_S,
        "n": n, "track": {"w": round(float((mx[0] - mn[0]) * scale), 1), "h": round(float((mx[1] - mn[1]) * scale), 1),
                          "pts": outline},
        "drivers": drivers, "weather": weather, "messages": messages, "track_status": status,
        **({"teams": {c: teams[c] for c in drivers if c in teams}} if teams else {}),
    }, notes


# ---------------------------------------------------------------- the run

def dumps(obj):
    return json.dumps(obj, separators=(",", ":"), allow_nan=False)


def export(db, lake, out, from_year=2022, sessions=("R", "Q"), only=None, force=False, log=print):
    db, lake, out = Path(db), Path(lake), Path(out)
    if not db.exists():
        sys.exit(f"REFUSING: database not found: {db}")
    marker = out / "index.json"
    if out.exists() and any(out.iterdir()):
        try:
            ok = json.loads(marker.read_text()).get("generator") == GENERATOR
        except (OSError, ValueError):
            ok = False
        if not ok:
            sys.exit(f"REFUSING: {out} is not empty and was not written by this script; nothing changed")
    out.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    con.execute(f"attach '{str(db).replace(chr(39), chr(39) * 2)}' as f1 (read_only)")
    wanted = con.execute(
        "select session_key, year, round, session_code from f1.gold.dim_session_circuit where year >= ? "
        f"and session_code in ({','.join('?' * len(sessions))}) order by year, round, session_code",
        [from_year, *sessions]).fetchall()
    pos = file_index(con, str(lake), "telemetry_pos")
    car = file_index(con, str(lake), "telemetry_car")
    weather = file_index(con, str(lake), "weather")
    results = file_index(con, str(lake), "results")
    rc = file_index(con, str(lake), "race_control")
    tstat = file_index(con, str(lake), "track_status")
    numbers = driver_numbers(con, str(lake))

    index = []
    raw = gz = 0
    largest = ("", 0)
    skipped = []
    todo = [w for w in wanted if (not only or w[0] in only)]
    started = time.time()
    for i, (key, y, r, code) in enumerate(todo, 1):
        k = (int(y), int(r), code)
        target = out / f"{key}.json"
        if target.exists() and not force:
            doc = json.loads(target.read_text())
            index.append({"key": key, "kind": doc["kind"], "n": doc["n"], "drivers": len(doc["drivers"])})
            raw += target.stat().st_size
            continue
        if k not in pos:
            skipped.append((key, "no position telemetry"))
            continue
        nums = numbers.get(k, {})
        if not nums:
            skipped.append((key, "no driver numbers for this session"))
            continue
        # the circuit is drawn from a lap the position data fully covers (it can stop before the session does)
        pos_lo, pos_hi = con.execute(
            "select min(session_time_s), max(session_time_s) from read_parquet(?) where session_time_s is not null "
            "and x is not null and y is not null and not (x = 0 and y = 0)", [pos[k][0]]).fetchone()
        if pos_lo is None:
            skipped.append((key, "no valid position samples (all missing or at 0, 0)"))
            continue
        window = con.execute(
            "select min(lap_start_time_s), max(time_s) from f1.gold.fct_lap where session_key = ?", [key]).fetchone()
        if window[0] is not None and window[1] is not None and window[1] > window[0]:
            covered = (min(pos_hi, window[1]) - window[0]) / (window[1] - window[0])
            if covered < MIN_COVERAGE:
                skipped.append((key, f"position data covers only {max(covered, 0):.0%} of the session"))
                continue
        inside = " and lap_start_time_s >= ? and lap_start_time_s + lap_time_s <= ?"
        fastest = con.execute(
            "select driver_code, lap_start_time_s, lap_time_s from f1.gold.fct_lap where session_key = ? and "
            "lap_time_s is not null and lap_start_time_s is not null and coalesce(is_clean_lap, false)" + inside +
            " order by lap_time_s limit 60", [key, pos_lo, pos_hi]).fetchall()
        if not fastest:
            fastest = con.execute(
                "select driver_code, lap_start_time_s, lap_time_s from f1.gold.fct_lap where session_key = ? and "
                "lap_time_s is not null and lap_start_time_s is not null" + inside + " order by lap_time_s limit 60",
                [key, pos_lo, pos_hi]).fetchall()
        info = {d: (int(n), e, s, lt) for d, n, e, s, lt in con.execute(
            "select driver_code, max(lap_number), arg_max(time_s, lap_number), arg_min(lap_start_time_s, lap_number), "
            "(array_agg(lap_time_s order by lap_number desc))[1] from f1.gold.fct_lap where session_key = ? group by driver_code",
            [key]).fetchall()}
        ends = {}
        for d, n, e in con.execute(
                "select driver_code, lap_number, time_s from f1.gold.fct_lap where session_key = ? and time_s is not null "
                "order by driver_code, lap_number", [key]).fetchall():
            ends.setdefault(d, []).append((int(n), float(e)))
        doc, notes = build_replay(
            con, key, code, pos[k][0], (car.get(k) or [None])[0], (weather.get(k) or [None])[0],
            (rc.get(k) or [None])[0], (tstat.get(k) or [None])[0], nums, info, fastest,
            driver_teams(con, results.get(k)), ends)
        if doc is None:
            skipped.append((key, "; ".join(notes)))
            continue
        last_lap_end = max([v[1] for v in info.values() if v[1] is not None] or [0])
        if pos_hi < last_lap_end - 120:
            notes.append(f"position data ends {(last_lap_end - pos_hi) / 60:.0f} min before the last lap does")
        text = dumps(doc)
        target.write_text(text)
        size = len(text.encode())
        zsize = len(gzip.compress(text.encode(), 6))
        raw += size
        gz += zsize
        if zsize > largest[1]:
            largest = (key, zsize)
        index.append({"key": key, "kind": doc["kind"], "n": doc["n"], "drivers": len(doc["drivers"])})
        log(f"[{i}/{len(todo)}] {key}: {size / 1e6:.2f} MB raw, {zsize / 1e6:.2f} MB gzipped"
            + (f"; {'; '.join(notes)}" if notes else "") + f"  ({time.time() - started:.0f}s)")
    marker.write_text(dumps({"generator": GENERATOR, "schema": SCHEMA, "step": STEP_S, "sessions": index}))
    return {"written": len(index), "skipped": skipped, "raw_bytes": raw, "gzip_bytes": gz, "largest": largest}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--lake", default=str(DEFAULT_LAKE))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--from-year", type=int, default=2022)
    ap.add_argument("--sessions", default="R,Q", help="comma-separated session codes, e.g. R,Q,S,SQ,SS")
    ap.add_argument("--only", nargs="*", help="session keys to export, e.g. 2026-R06-R")
    ap.add_argument("--force", action="store_true", help="rewrite sessions that already have a file")
    a = ap.parse_args(argv)
    r = export(a.db, a.lake, a.out, a.from_year, tuple(s for s in a.sessions.split(",") if s), a.only, a.force)
    print(f"\n{r['written']} replay files in {a.out}")
    print(f"this run wrote {r['raw_bytes'] / 1e6:.1f} MB raw, about {r['gzip_bytes'] / 1e6:.1f} MB gzipped "
          f"(largest: {r['largest'][0] or '-'} at {r['largest'][1] / 1e6:.2f} MB gzipped)")
    if r["skipped"]:
        print(f"{len(r['skipped'])} sessions skipped:")
        for k, why in r["skipped"][:20]:
            print(f"  {k}: {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
