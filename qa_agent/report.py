"""Turn the files in qa_agent/results/ into qa_agent/results/RESULTS.md.

    python -m qa_agent.report
"""
import json
from pathlib import Path

RES = Path(__file__).resolve().parent / "results"


def pct(x):
    return "-" if x is None else f"{x * 100:.0f}%"


def main():
    base = [json.loads(p.read_text()) for p in sorted(RES.glob("baseline/*.json"))]
    for r in base:
        r["model"] = r["model"] + " (first prompts)"
    runs = [json.loads(p.read_text()) for p in sorted(RES.glob("*.json"))] + base
    fresh = [json.loads(p.read_text()) for p in sorted(RES.glob("fresh/*.json"))]
    if not runs:
        raise SystemExit("no results yet: run python -m qa_agent.run_eval --model <name>")
    L = ["# Question-answering agent: results", ""]
    s0 = runs[0]["summary"]
    L += [f"{s0['questions']} questions: {s0['answerable']} the data can answer and {s0['unanswerable']} it cannot. "
          "Answers are scored by running the agent's SQL and comparing the result table with a reference query "
          "(execution accuracy). A question the data cannot answer is correct only if the agent declines.", ""]
    L += ["| Model | Run | Correct (answerable) | Declined correctly | Answered the unanswerable? | Declined the answerable | Right tables | Valid first try | Seconds per question |",
          "|---|---|---|---|---|---|---|---|---|"]
    for r in runs:
        s = r["summary"]
        L.append(f"| {r['model']} | {r['date']} | {s['correct_answerable']} of {s['answerable']} ({pct(s['accuracy'])}) | "
                 f"{s['correct_refusals']} of {s['unanswerable']} | {s['unanswerable'] - s['correct_refusals']} | "
                 f"{s['over_refusals']} of {s['answerable']} | {pct(s['route_recall'])} | {pct(s['first_try_valid'])} | {s['mean_seconds']} |")
    L += ["", "## By category", "", "| Category | " + " | ".join(r["model"] for r in runs) + " |", "|---|" + "---|" * len(runs)]
    cats = sorted({c for r in runs for c in r["summary"]["by_category"]})
    for c in cats:
        cells = []
        for r in runs:
            v = r["summary"]["by_category"].get(c)
            cells.append(f"{v['correct']} of {v['n']}" if v else "-")
        L.append(f"| {c} | " + " | ".join(cells) + " |")
    for r in [r for r in runs if "first prompts" not in r["model"]]:
        bad = [x for x in r["records"] if not x["correct"]]
        L += ["", f"## Failures: {r['model']} ({len(bad)})", ""]
        for x in bad:
            L.append(f"- **{x['id']}** ({x['category']}): {x['question']}")
            if x["answerable"]:
                if x["refused"]:
                    L.append(f"  - declined: {x['reason']}")
                elif not x["executed"]:
                    L.append(f"  - no working query. Errors: {'; '.join(x['errors'][-2:]) or 'none'}")
                else:
                    L.append(f"  - got {x['rows'][:3]}, expected {x['ref_rows'][:3]}")
            else:
                L.append(f"  - answered anyway with `{x['sql']}` returning {x['rows'][:3]}")
    if fresh:
        f0 = fresh[0]["summary"]
        L += ["", "## Fresh question set", "",
              f"{f0['questions']} questions written after the prompts were frozen ({f0['answerable']} answerable, {f0['unanswerable']} not), "
              "run once per model with no prompt changes afterwards.", "",
              "| Model | Run | Prompts | Correct (answerable) | Declined correctly | Declined the answerable | Right tables | Valid first try | Seconds per question |",
              "|---|---|---|---|---|---|---|---|---|"]
        for r in fresh:
            s = r["summary"]
            L.append(f"| {r['model']} | {r['date']} | {r.get('prompt_version', '?')} | {s['correct_answerable']} of {s['answerable']} ({pct(s['accuracy'])}) | "
                     f"{s['correct_refusals']} of {s['unanswerable']} | {s['over_refusals']} of {s['answerable']} | "
                     f"{pct(s['route_recall'])} | {pct(s['first_try_valid'])} | {s['mean_seconds']} |")
        L += ["", "| Category | " + " | ".join(r["model"] for r in fresh) + " |", "|---|" + "---|" * len(fresh)]
        for c in sorted({c for r in fresh for c in r["summary"]["by_category"]}):
            cells = []
            for r in fresh:
                v = r["summary"]["by_category"].get(c)
                cells.append(f"{v['correct']} of {v['n']}" if v else "-")
            L.append(f"| {c} | " + " | ".join(cells) + " |")
        for r in fresh:
            bad = [x for x in r["records"] if not x["correct"]]
            L += ["", f"### Fresh set failures: {r['model']} ({len(bad)})", ""]
            for x in bad:
                L.append(f"- **{x['id']}** ({x['category']}): {x['question']}")
                if x["answerable"]:
                    if x["refused"]:
                        L.append(f"  - declined: {x['reason']}")
                    elif not x["executed"]:
                        L.append(f"  - no working query. Errors: {'; '.join(x['errors'][-2:]) or 'none'}")
                    else:
                        L.append(f"  - got {x['rows'][:3]}, expected {x['ref_rows'][:3]}")
                else:
                    L.append(f"  - answered anyway with `{x['sql']}` returning {x['rows'][:3]}")
    (RES / "RESULTS.md").write_text("\n".join(L) + "\n")
    print("wrote", RES / "RESULTS.md")


if __name__ == "__main__":
    main()
