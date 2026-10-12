#!/usr/bin/env bash
# Experiments on the race-state engine: where do lap boundaries land on the reference line,
# and do two candidate fixes help? Patches engine_probe.py (safe: stops if text does not match).
# Run from anywhere:  bash engine_experiments.sh
set -u
cd ~/Desktop/f1-pitwall || exit 1

python - <<'PYEOF'
from pathlib import Path

p = Path("engine_probe.py")
s = p.read_text()

OLD_PROJECT = '''    s_out, d_out = np.empty(len(xy)), np.empty(len(xy))
    for lo in range(0, len(xy), 20000):
        p = xy[lo:lo + 20000]
        d2 = ((p[:, None, :] - ref[None, :, :]) ** 2).sum(2)
'''
NEW_PROJECT = '''    s_out, d_out = np.empty(len(xy)), np.empty(len(xy))
    if HEADING:
        v = np.empty_like(xy)
        v[1:-1] = xy[2:] - xy[:-2]
        v[0], v[-1] = v[1], v[-2]
        speed = np.sqrt((v ** 2).sum(1))
        unit = v / np.maximum(speed, 1e-9)[:, None]
        tan = np.vstack([ab, ab[-1:]])
        tan = tan / np.maximum(np.sqrt((tan ** 2).sum(1)), 1e-9)[:, None]
    for lo in range(0, len(xy), 20000):
        p = xy[lo:lo + 20000]
        d2 = ((p[:, None, :] - ref[None, :, :]) ** 2).sum(2)
        if HEADING:
            cos = unit[lo:lo + 20000] @ tan.T
            moving = (speed[lo:lo + 20000] > 20)[:, None]
            d2 = d2 + np.where(moving & (cos < 0.3), 1e12, 0.0)
'''
BOUNDS = '''

bd = os.environ.get("BOUNDS_DRIVER")
if bd:
    dl = laps[laps["Driver"] == bd].sort_values("LapNumber").drop_duplicates("LapNumber")
    p = (pos[pos["driver_number"] == int(dl["DriverNumber"].iloc[0])]
         .sort_values("session_time_s").drop_duplicates("session_time_s"))
    t = p["session_time_s"].to_numpy(float)
    s_raw, _ = project(p[["x", "y"]].to_numpy(float), ref_xy, s_ref)
    S = np.unwrap(s_raw, period=L)
    vals = [f"{int(r.LapNumber)}:{(np.interp(r.Time_s, t, S) / L) % 1:.2f}"
            for r in dl.itertuples() if pd.notna(r.Time_s)]
    print(f"WHERE EACH LAP ENDS ON THE REFERENCE LINE ({bd}), lap:position, 0.00 = on the line")
    print("  " + "  ".join(vals))
'''
edits = [
    ("import sys\nimport time\n", "import os\nimport sys\nimport time\n"),
    ('LAKE = "data/lake"\n',
     'LAKE = "data/lake"\nHEADING = os.environ.get("HEADING") == "1"\n'
     'BAND = float(os.environ.get("BAND", "0.4"))\n'),
    ("        if 0.6 * L <= span <= 1.4 * L:\n",
     "        if (1 - BAND) * L <= span <= (1 + BAND) * L:\n"),
    (OLD_PROJECT, NEW_PROJECT),
]
if "HEADING = os.environ" in s:
    print("engine_probe.py is already patched")
else:
    for old, new in edits:
        if s.count(old) != 1:
            print("COULD NOT PATCH engine_probe.py: expected one match for:\n", old[:80])
            raise SystemExit(1)
        s = s.replace(old, new)
    if "BOUNDS_DRIVER" not in s:
        s = s.rstrip("\n") + "\n" + BOUNDS
    p.write_text(s)
    print("engine_probe.py patched")
PYEOF
[ $? -ne 0 ] && exit 1
python -m py_compile engine_probe.py || { echo "engine_probe.py does not compile"; exit 1; }

echo
echo "##### WHERE EACH LAP ENDS ON THE REFERENCE LINE #####"
for spec in "2026 4 R HAD" "2026 4 R SAI" "2026 17 S BOR" "2026 17 R VER"; do
  set -- $spec
  echo "--- $1 round $2 $3, driver $4"
  BOUNDS_DRIVER=$4 python engine_probe.py $1 $2 $3 | tail -n 2
done

echo
echo "##### FIX EXPERIMENTS: engine exact-order % at sector line 1, then line 2 #####"
for race in "2026 4 R" "2026 17 S" "2026 17 R"; do
  for variant in "plain" "BAND=0.08" "HEADING=1" "HEADING=1 BAND=0.08"; do
    echo "=== $race | $variant"
    if [ "$variant" = "plain" ]; then
      python engine_probe.py $race | grep "engine (GPS"
    else
      env $variant python engine_probe.py $race | grep "engine (GPS"
    fi
  done
done
echo
echo "done"
