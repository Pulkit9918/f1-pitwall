"""Run the evaluation set against a model served by Ollama.

    python -m qa_agent.run_eval --model qwen2.5-coder:7b
    python -m qa_agent.run_eval --model qwen2.5-coder:14b --only winner_2025_italy,next_race_winner
Writes qa_agent/results/<model>.json. Then:  python -m qa_agent.report
"""
import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

from . import agent as ag
from . import db, evaluate
from .questions import QUESTIONS

ROOT = Path(__file__).resolve().parents[1]


def reference(con, q):
    cols, rows, _ = db.run(con, q.sql, timeout_s=60, max_rows=10_000)
    return rows


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--db", default=str(ROOT / "data" / "f1_dbt.duckdb"))
    p.add_argument("--manifest", default=str(ROOT / "dbt" / "target" / "manifest.json"))
    p.add_argument("--host", default="http://localhost:11434")
    p.add_argument("--num-ctx", type=int, default=12288)
    p.add_argument("--only", help="comma-separated question ids")
    p.add_argument("--limit", type=int)
    p.add_argument("--out")
    a = p.parse_args(argv)

    con = db.connect(a.db)
    cards = ag.load_cards(con, a.manifest)
    if not Path(a.manifest).exists():
        print("note: no dbt manifest, so the model sees column names and types but no descriptions", file=sys.stderr)
    agent = ag.Agent(con, ag.Ollama(a.model, a.host, a.num_ctx), cards)
    qs = [q for q in QUESTIONS if not a.only or q.id in a.only.split(",")][: a.limit]
    records = []
    for i, q in enumerate(qs, 1):
        try:
            out = agent.answer(q.question)
        except Exception as e:  # a model or network error must not stop the run
            print(f"[{i}/{len(qs)}] {q.id}: model call failed: {e}")
            raise SystemExit("Is Ollama running and the model pulled? (ollama list)")
        ref = reference(con, q) if q.answerable else None
        s = evaluate.score(q, out, ref)
        records.append({**s, "question": q.question, "sql": out.sql, "reason": out.reason, "errors": out.errors,
                        "rows": [list(map(str, r)) for r in out.rows[:5]], "ref_rows": [list(map(str, r)) for r in (ref or [])[:5]]})
        print(f"[{i}/{len(qs)}] {q.id}: {'ok' if s['correct'] else 'WRONG'} ({out.seconds}s)")
    summary = evaluate.summarise([{k: v for k, v in r.items() if k in
                                   {"id", "category", "answerable", "refused", "executed", "attempts", "seconds", "tables",
                                    "route_recall", "route_precision", "first_try", "correct", "no_data"}} for r in records])
    out_path = Path(a.out) if a.out else ROOT / "qa_agent" / "results" / (re.sub(r"[^\w.-]+", "_", a.model) + ".json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"model": a.model, "date": dt.date.today().isoformat(), "num_ctx": a.num_ctx, "prompt_version": ag.PROMPT_VERSION,
                                    "summary": summary, "records": records}, indent=1))
    print(json.dumps(summary, indent=1))
    print("wrote", out_path)


if __name__ == "__main__":
    main()
