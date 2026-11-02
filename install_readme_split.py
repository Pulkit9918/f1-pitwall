#!/usr/bin/env python3
"""Split the long README into a short front page and docs/*.md. The detail is moved word for word, none is deleted.
Run from the repository root:  python3 install_readme_split.py
Refuses, changing nothing, if a docs file already exists or the README's sections are not the ones expected."""
import re
import sys
from pathlib import Path

DOCS = {
    "docs/data.md": ("Data and ingestion", ["Data", "Ingestion", "What the data-quality checks found (raw feed)"]),
    "docs/dbt.md": ("The dbt layer, reconciliation and known data gaps", ["Transformation layer (dbt)"]),
    "docs/engine-and-models.md": ("Race-state engine and strategy models", ["Race-state engine", "Strategy models"]),
    "docs/apps.md": ("The apps, the API and Airflow", ["The Streamlit app", "Web app", "The API", "Orchestration (Airflow)"]),
    "docs/qa-agent.md": ("Question-answering agent", ["Question-answering agent"]),
    "docs/decisions-and-limits.md": ("Decisions, limitations and roadmap", ["Why it exists", "Decisions and dead ends", "Limitations", "Roadmap"]),
    "docs/data-terms.md": ("Data terms", ["Data terms"]),
}
KEEP = ["What it does", "Architecture", "Run it locally", "Repository layout", "Credits and licence"]

FRONT_TOP = """# F1 Pitwall

![CI](https://github.com/Pulkit9918/f1-pitwall/actions/workflows/ci.yml/badge.svg)
![dbt](https://github.com/Pulkit9918/f1-pitwall/actions/workflows/dbt.yml/badge.svg)

Race-strategy analytics for Formula 1 on a local Parquet lakehouse: a resumable ingestion pipeline, a tested dbt layer, a race-state engine rebuilt from GPS, a pit-stop predictor, a Streamlit app, a read-only API and a static web app with a race replay.

Most F1 tools are viewers. This project asks a narrower question: *how well can the numbers on a timing screen be reconstructed and used for strategy decisions, and how do we know?* Every derived number comes with a test against something independent (official sector timing, the official classification, real pit stops), and the limits are written down.

> **Unofficial.** Not associated with the Formula 1 companies. F1, FORMULA ONE, FORMULA 1, GRAND PRIX and related marks are trade marks of Formula One Licensing B.V. Data comes from the public timing feed via [FastF1](https://github.com/theOehrly/Fast-F1) and from the [Jolpica](https://github.com/jolpica/jolpica-f1) Ergast-compatible API. The raw data, the lake and the database are not in this repository. It does include derived JSON that the web app reads under `web/public`; I have not confirmed that publishing that is permitted (see [Data terms](docs/data-terms.md)). Personal, non-commercial use.

## Results at a glance

| Part | Result | Details |
|---|---|---|
| Ingest | 706 sessions, 2018-2026, about 1.8 GB of zstd Parquet. Every attempt is in an audit log; data contracts are checked on every table before it is written | [data.md](docs/data.md) |
| dbt on DuckDB | 57 models, 1 seed and 200 tests: 251 of 258 steps passed, 7 warnings, 0 errors. 26 gold models have enforced contracts; a documentation-coverage gate runs in CI | [dbt.md](docs/dbt.md) |
| Race-state engine | Running order rebuilt from GPS and checked against official sector timing on 135 sessions: median exact order 97.2% at the first sector line (85.9% for a last-lap baseline) and 99.7% at the second (86.1%). It fails at the second line at Baku and Suzuka | [engine-and-models.md](docs/engine-and-models.md) |
| Pit-stop predictor | Scored on races it was not fitted on: 41.1% exact place over 5,489 green-flag stops, and 79.4% on the 649 undisturbed stops, which are 12% of all stops | [apps.md](docs/apps.md) |
| Q&A agent | A local 14B model answering questions with SQL: 25 of 28 on questions written after the prompts were frozen, and it declined all 8 that the data cannot answer | [qa-agent.md](docs/qa-agent.md) |

## Limits to know first

- **New sessions cannot be ingested at the moment.** Since about 15 October 2026 F1's timing archive wants a login. The lake is complete through round 17 of 2026 (Singapore); everything downstream works on it.
- **The pit-stop predictor gets the exact place right about four times in ten.** In most stops other cars are also pitting and the model does not account for them.
- **Some results are unexplained.** The data gaps, and the warnings left in the dbt build, are listed with what was measured, in [dbt.md](docs/dbt.md).
- **Publishing the derived JSON is a risk I have not resolved.** See [Data terms](docs/data-terms.md).

The full list is in [decisions-and-limits.md](docs/decisions-and-limits.md).

"""

DOC_INDEX = """## Documentation

| File | What is in it |
|---|---|
| [docs/data.md](docs/data.md) | Coverage, lake layout, ingestion and rate limits, and what the data-quality checks found in the raw feed |
| [docs/dbt.md](docs/dbt.md) | The silver and gold models, reconciliation, race control periods, telemetry coverage, known data gaps |
| [docs/engine-and-models.md](docs/engine-and-models.md) | The race-state engine and its validation, pit loss, rejoin prediction, tyre degradation, undercuts |
| [docs/apps.md](docs/apps.md) | The Streamlit app, the web app and its replay, the API, and the Airflow DAG |
| [docs/qa-agent.md](docs/qa-agent.md) | The question-answering agent and its two evaluation sets |
| [docs/decisions-and-limits.md](docs/decisions-and-limits.md) | Decisions and dead ends, limitations, roadmap |
| [docs/data-terms.md](docs/data-terms.md) | What I found about data terms |

"""

text = Path("README.md").read_text(encoding="utf-8") if Path("README.md").exists() else ""
problems = []
if not text:
    problems.append("README.md not found (run from the repository root)")
for f in DOCS:
    if Path(f).exists():
        problems.append(f"{f} already exists")
parts = re.split(r"(?m)^## (.+)$", text)
secs = {}
for i in range(1, len(parts), 2):
    name = parts[i].strip()
    if name in secs:
        problems.append(f"section appears twice: {name}")
    secs[name] = parts[i + 1].strip("\n")
want = set(KEEP) | {s for _, ss in DOCS.values() for s in ss}
for n in sorted(want - set(secs)):
    problems.append(f"README section not found: {n}")
for n in sorted(set(secs) - want):
    problems.append(f"README section I do not know where to put: {n}")
if problems:
    print("REFUSING, nothing changed:")
    print("\n".join("  " + p for p in problems))
    sys.exit(1)


def fix_links(s):
    return s.replace("](qa_agent/results/RESULTS.md)", "](../qa_agent/results/RESULTS.md)").replace("docs/img/", "img/")


out = {}
for path, (title, names) in DOCS.items():
    body = "\n\n".join(f"## {n}\n\n{secs[n]}" for n in names)
    out[path] = f"# {title}\n\n[Back to the README](../README.md)\n\n{fix_links(body)}\n"
front = FRONT_TOP
for n in ("What it does", "Architecture", "Run it locally"):
    front += f"## {n}\n\n{secs[n]}\n\n"
front += DOC_INDEX
for n in ("Repository layout", "Credits and licence"):
    front += f"## {n}\n\n{secs[n]}\n\n"
out["README.md"] = front.rstrip("\n") + "\n"

Path("docs").mkdir(exist_ok=True)
for f, t in out.items():
    Path(f).write_text(t, encoding="utf-8")
print(f"README.md is now {out['README.md'].count(chr(10))} lines (was {text.count(chr(10))}).")
for f in DOCS:
    print(f"  {f}: {out[f].count(chr(10))} lines")
print("Read README.md, then:  git add -A && git commit -m 'README: short front page, detail moved to docs/'")
