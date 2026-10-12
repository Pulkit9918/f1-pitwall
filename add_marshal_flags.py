#!/usr/bin/env python3
"""Marshal-sector yellow flags on the Race scrubber map. Safe to run twice.

Each marshal sector under a yellow flag is drawn in yellow (orange for double yellow) while it is
active, from the race control messages. Needs the circuit's marshal-sector points and the clock
mapping from the position data; if either is missing or looks wrong, the feature switches itself off.
Run from the project folder:  python add_marshal_flags.py
"""

import py_compile
import sys
from pathlib import Path

ROOT = Path.cwd()
PAGE = "app/pages/8_Race_scrubber.py"
if not (ROOT / PAGE).exists():
    sys.exit("Run this from ~/Desktop/f1-pitwall (the scrubber page was not found here).")


def note(ok: bool, msg: str) -> None:
    print(("OK       " if ok else "SKIPPED  ") + msg)


def patch(old: str, new: str, label: str) -> None:
    f = ROOT / PAGE
    s = f.read_text()
    if new in s:
        note(True, f"{label}: already applied")
        return
    n = s.count(old)
    if n != 1:
        note(False, f"{label}: expected 1 match, found {n}; file not changed")
        return
    f.write_text(s.replace(old, new))
    note(True, f"{label}: applied")


HELPERS = '''@st.cache_data(show_spinner=False)
def utc_offset(year: int, rnd: int, code: str):
    """UTC clock time of session second zero, from the first position sample."""
    path = pw.part("telemetry_pos", year, rnd, code)
    con = duckdb.connect()
    try:
        d, s = con.sql("SELECT date_utc, session_time_s FROM read_parquet('" + str(path) + "') "
                       "ORDER BY session_time_s LIMIT 1").fetchone()
    finally:
        con.close()
    return pd.Timestamp(d) - pd.Timedelta(seconds=float(s))


def build_marshal():
    """Marshal-sector extents along the reference line, and yellow / clear events in session seconds."""
    ms = pw.read("circuit_marshal_sectors", year, rnd, code)
    rc_all = pw.read("race_control", year, rnd, code)
    if ms.empty or rc_all.empty or not {"X", "Y", "Number"} <= set(ms.columns):
        return None
    if not {"Time", "Scope", "Flag", "Sector"} <= set(rc_all.columns):
        return None
    s_pts, off = eg.project(ms[["X", "Y"]].to_numpy(float), state["ref_xy"], _s)
    if float(np.median(off)) > 500:        # over 50 m from the track: a different coordinate frame
        return None
    frac = s_pts / _s[-1]
    order = np.argsort(frac)
    starts = frac[order]
    ends = np.roll(starts, -1)
    ends[-1] += 1.0
    nums = ms["Number"].to_numpy()[order].astype(int)
    extents = {int(n): (float(a), float(b)) for n, a, b in zip(nums, starts, ends)}
    ev = rc_all[rc_all["Scope"].isin(["Sector", "Track"]) & rc_all["Flag"].notna()].copy()
    ev["t"] = (pd.to_datetime(ev["Time"]) - utc_offset(year, rnd, code)).dt.total_seconds()
    ev = ev.sort_values("t")
    events = []
    for r in ev.itertuples():
        flag = str(r.Flag).upper()
        if r.Scope == "Track" and flag == "CLEAR":
            events.append((float(r.t), "all", "CLEAR"))
        elif r.Scope == "Sector" and pd.notna(r.Sector):
            events.append((float(r.t), int(r.Sector), flag))
    inside = [e for e in events if -600 <= e[0] <= state["end"] + 1800]
    if not inside:                          # the clock mapping looks wrong: switch the feature off
        return None
    return {"extents": extents, "events": inside}


marshal = build_marshal()


def yellow_now(t_now):
    active = {}
    for t, who, flag in marshal["events"]:
        if t > t_now:
            break
        if who == "all":
            active = {}
        elif flag in ("YELLOW", "DOUBLE YELLOW"):
            active[who] = flag
        elif flag == "CLEAR":
            active.pop(who, None)
    return active


'''

CARS_ANCHOR = '    followed = snap["driver"].isin(follow)\n    dim = 0.65 if follow else 1.0\n'
DRAW = '''    if marshal is not None:
        for num_, flag_ in yellow_now(T).items():
            ext = marshal["extents"].get(num_)
            if ext is None:
                continue
            pts = tr(np.array([point_at(f_) for f_ in np.linspace(ext[0], ext[1], 30)]))
            fig.add_trace(go.Scatter(
                x=pts[:, 0], y=pts[:, 1], mode="lines", showlegend=False, hoverinfo="text",
                hovertext=f"{flag_.title()} in marshal sector {num_}",
                line=dict(color="#ff9f1c" if flag_ == "DOUBLE YELLOW" else "#ffd60a", width=13)))
'''

patch("import re\nimport time\n", "import re\nimport time\n\nimport duckdb\n", "imports")
patch("@st.cache_data(show_spinner=False)\ndef car_arrays(year: int, rnd: int, code: str, num: int):\n",
      HELPERS + "@st.cache_data(show_spinner=False)\ndef car_arrays(year: int, rnd: int, code: str, num: int):\n",
      "marshal-sector helpers")
patch(CARS_ANCHOR, DRAW + CARS_ANCHOR, "yellow stretches on the map")
patch('            "- **Compare gaps against:**',
      '            "- **Yellow track stretches:** marshal sectors under a yellow flag at this moment '
      '(orange for double yellow), from the race control messages, with the message sector numbers '
      'matched to the circuit\'s marshal sectors. Shown only for circuits with marshal-sector data.\\n"\n'
      '            "- **Compare gaps against:**',
      "legend entry")

try:
    py_compile.compile(str(ROOT / PAGE), doraise=True)
    print("\n  ok       scrubber page compiles\nDone. Reload the app in your browser.")
except py_compile.PyCompileError as e:
    print("\n  SYNTAX ERROR ->", str(e)[:300], "\nSend me this output.")
