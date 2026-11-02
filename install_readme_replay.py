#!/usr/bin/env python3
"""README updates for the replay upgrades, the 2 November 2026 ingest check, and the replay data size.
Run from the repository root:  python3 install_readme_replay.py
Refuses, changing nothing, if an anchor is not found exactly once (so it will not run twice)."""
import sys
from pathlib import Path

EDITS = {
    "README.md": [
        (
            "| Replay (`/replay`) | All cars on the track map with playback, leaderboard and gaps, driver telemetry cards, weather, flags and race control messages, for race and qualifying sessions from 2022 (sprints with `--sessions`) | `export_replay.py` |",
            "| Replay (`/replay`) | All cars on the track map with playback, corner numbers, marshal-sector flags, a leaderboard with gaps, tyre history and pit timers, a timing tower, driver telemetry cards, weather, flags and race control messages, for race, qualifying, sprint and sprint-qualifying sessions from 2022 (267 replays) | `export_replay.py` |",
        ),
        (
            "`web/public/replay-data` (about 440 MB)",
            "`web/public/replay-data` (about 500 MB)",
        ),
        (
            "so shorter freezes are not marked.\n",
            "so shorter freezes are not marked.\n"
            "\n"
            "**What the page shows.** The leaderboard gives the gap to the leader and to the car ahead (an interval under a second is highlighted), "
            "each driver's earlier tyre compounds, a pit-lane timer while a car is in the pits, and a badge for the holder of the fastest lap so far. "
            "The timing tower has Gap and Int columns next to the sector colours, and the lap history tab has a chart of the gaps. "
            "The controls have 0.5x to 20x playback, skip buttons (including 5 minutes back and forward), a jump to a lap number, a progress bar shaded for yellow-flag, safety car, VSC and red-flag periods, "
            "and during a red flag a button that skips to the restart. A safety car or VSC makes the track edge pulse and labels the map; "
            "there is no safety car on the map, because the data has no position for it.\n"
            "\n"
            "**Corner numbers and marshal sectors.** Corner numbers come from the lake's `circuit_corners` table and are placed on the drawn outline; "
            "a checkbox hides them. A marshal sector is the stretch of track from one marshal post to the next (`circuit_marshal_sectors`). "
            "While a message such as \"YELLOW IN TRACK SECTOR 7\" is in force, that sector is highlighted and tagged, "
            "yellow, or orange for a double yellow, until its \"CLEAR\" message. A corner is used only if it lies close to the drawn circuit, "
            "and the exporter drops all corners when a quarter or more are far away, and all marshal sectors when any post is far away or the posts do not run once around the lap in order, "
            "because a label in the wrong place is worse than none. That happens in nine replays from four weekends: "
            "2022 round 21 has neither corners nor sectors, and 2022 round 18, 2023 round 16 and 2024 round 4 have no sectors. "
            "I did not look into why, and have not checked the sector highlights against the broadcast.\n",
        ),
        (
            "later sessions cannot be loaded until access changes.",
            "later sessions cannot be loaded until access changes. "
            "On 2 November 2026 I tried the United States and Mexico City weekends (nine sessions): FastF1 3.8.3 could not load any of them, and all nine are recorded as failed in the ingest log. "
            "FastF1 3.9.0 adds a sign-in with an F1TV account for this, and says an F1TV Access subscription or higher is needed; loading the United States race with it went straight to a sign-in prompt. "
            "I did not sign in, did not upgrade the project's environment, and have not checked whether the F1TV terms allow automated use.",
        ),
        (
            "- Mark stale or frozen car positions on the replay (2026 round 11), and a formation-lap marker\n",
            "- Find out why the circuit data does not line up in the four weekends listed under Replay, and add a formation-lap marker to the replay\n",
        ),
        (
            "| 2023 round 17, sprint shootout | Car and position telemetry both start 78 s after the first lap began | Source gap, caught by `telemetry_coverage_flags`; cause unknown |\n",
            "| 2023 round 17, sprint shootout | Car and position telemetry both start 78 s after the first lap began | Source gap, caught by `telemetry_coverage_flags`; cause unknown |\n"
            "| 2022 rounds 18 and 21, 2023 round 16, 2024 round 4 (nine replays) | The replay export drops the corner numbers or the marshal sectors: the corner coordinates are far from the drawn circuit (round 21), or the marshal posts do not run once around the lap in order (the others) | Not investigated |\n",
        ),
        (
            "- The simulated safety car is placed about 500 m ahead of the leader (no safety car GPS exists).",
            "- The simulated safety car is placed about 500 m ahead of the leader (no safety car GPS exists). The web replay does not draw one; it shows the safety car as a pulsing track edge and a label.",
        ),
    ],
    "web/README.md": [
        (
            "Pages: `/` (latest race), `/sessions`, `/circuits`, `/race/?key=2026-R17-R` (one session).",
            "Pages: `/` (latest race), `/sessions`, `/circuits`, `/race/?key=2026-R17-R` (one session), `/telemetry`, `/compare`, `/predictor`, `/practice`,\n"
            "and `/replay` (race, qualifying and sprint replays; `python scripts/export_replay.py --sessions R,Q,S,SQ,SS` builds its data).",
        ),
    ],
}

problems, new = [], {}
for f, edits in EDITS.items():
    p = Path(f)
    if not p.exists():
        problems.append(f"{f}: not found (run from the repository root)")
        continue
    t = p.read_text(encoding="utf-8")
    for old, rep in edits:
        n = t.count(old)
        if n != 1:
            problems.append(f"{f}: text found {n} times: {old[:80]!r}")
        else:
            t = t.replace(old, rep)
    new[f] = t
if problems:
    print("REFUSING, nothing changed:")
    print("\n".join("  " + x for x in problems))
    sys.exit(1)
for f, t in new.items():
    Path(f).write_text(t, encoding="utf-8")
print("README.md and web/README.md updated. Read the diff before committing:  git diff README.md web/README.md")
