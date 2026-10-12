#!/usr/bin/env python3
"""Adopts the stricter lap-length check in the scrubber's engine and flags estimated laps.

Laps whose GPS span is not within 8% of the track length use timing-based progress instead, and the
timing tower shows a ~ after the gap for cars on such a lap. Safe to run twice.
Run from the project folder:  python patch_engine_band.py
"""

import py_compile
import sys
from pathlib import Path

ROOT = Path.cwd()
if not (ROOT / "app" / "engine.py").exists():
    sys.exit("Run this from ~/Desktop/f1-pitwall (app/engine.py not found here).")


def note(ok: bool, msg: str) -> None:
    print(("OK       " if ok else "SKIPPED  ") + msg)


def patch(path: str, old: str, new: str, label: str) -> None:
    f = ROOT / path
    if not f.exists():
        note(False, f"{label}: {path} does not exist")
        return
    s = f.read_text()
    if new in s:
        note(True, f"{label}: already applied")
        return
    n = s.count(old)
    if n != 1:
        note(False, f"{label}: expected 1 match in {path}, found {n}; file not changed")
        return
    f.write_text(s.replace(old, new))
    note(True, f"{label}: applied")


ENG = "app/engine.py"
patch(ENG,
      '        P = np.full(len(t), np.nan)\n        prev_end = None\n',
      '        P = np.full(len(t), np.nan)\n        approx = set()\n        prev_end = None\n',
      "engine: track laps estimated from timing")
patch(ENG,
      '            if 0.6 * L <= span <= 1.4 * L:\n'
      '                frac = (S[m] - s0) / span\n'
      '            else:\n'
      '                frac = (t[m] - t0) / (t1 - t0)\n',
      '            if 0.92 * L <= span <= 1.08 * L:\n'
      '                frac = (S[m] - s0) / span\n'
      '            else:\n'
      '                frac = (t[m] - t0) / (t1 - t0)\n'
      '                approx.add(int(r.LapNumber))\n',
      "engine: stricter lap-length check")
patch(ENG,
      '            "max_lap": int(dls["LapNumber"].max()),\n',
      '            "max_lap": int(dls["LapNumber"].max()),\n            "approx": approx,\n',
      "engine: store estimated laps")
patch(ENG,
      '            "status": status, "P": r["P"], "x": r["x"], "y": r["y"],\n',
      '            "status": status, "approx": (n_done + 1) in d["approx"],\n'
      '            "P": r["P"], "x": r["x"], "y": r["y"],\n',
      "engine: expose the estimated flag")

PAGE = "app/pages/8_Race_scrubber.py"
patch(PAGE,
      'table = snap.rename(columns={"tyre_age": "age", "last_lap": "last lap", "best_lap": "best lap"})\n',
      'table = snap.rename(columns={"tyre_age": "age", "last_lap": "last lap", "best_lap": "best lap"})\n'
      'table["gap"] = [g + " ~" if (a and g) else g for g, a in zip(table["gap"], snap["approx"])]\n',
      "scrubber: mark estimated gaps")
f = ROOT / PAGE
if f.exists() and "estimated from the lap timing" not in f.read_text():
    f.write_text(f.read_text().rstrip("\n") + '\n'
                 'st.caption("A ~ after a gap means GPS matching looked unreliable on that car\'s current '
                 'lap (a pit-lane lap, an incident or a mismatch near the line), so its progress is '
                 'estimated from the lap timing instead.")\n')
    note(True, "scrubber: explanation caption added")

patch("engine_probe.py", 'BAND = float(os.environ.get("BAND", "0.4"))',
      'BAND = float(os.environ.get("BAND", "0.08"))', "probe: new default lap-length check")

print("\nChecking that everything still compiles:")
bad = 0
for name in (ENG, PAGE, "engine_probe.py"):
    try:
        py_compile.compile(str(ROOT / name), doraise=True)
        print("  ok      ", name)
    except py_compile.PyCompileError as e:
        bad += 1
        print("  SYNTAX ERROR in", name, "->", str(e)[:300])
print("\nDone. If the scrubber looks unchanged, clear its cache (top-right menu > Clear cache)."
      if not bad else "\nSend me this output.")
