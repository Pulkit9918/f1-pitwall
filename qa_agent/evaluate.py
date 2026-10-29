"""Scoring one answer and summarising a run."""
from collections import defaultdict

from . import compare
from .agent import ALWAYS
from .questions import Question


def score(q: Question, out, ref_rows) -> dict:
    executed = bool(out.sql) and not out.refused and (bool(out.columns) or bool(out.rows))
    s = {"id": q.id, "category": q.category, "answerable": q.answerable, "refused": out.refused, "executed": executed,
         "attempts": out.attempts, "seconds": out.seconds, "tables": out.tables}
    if q.answerable:
        want, got = set(q.tables) - set(ALWAYS), set(out.tables)
        s["route_recall"] = want <= got
        s["route_precision"] = (len(want & got) / len(got)) if got else 0.0
        s["first_try"] = executed and out.attempts == 1
        s["correct"] = bool(executed and compare.matches(ref_rows, out.rows, q.ordered, q.tol))
    else:
        # right: decline, or run a query that finds nothing (empty or all NULL) and so reports no answer; wrong: a value
        s["no_data"] = bool(executed and not any(v is not None for r in out.rows for v in r))
        s["correct"] = bool(out.refused or s["no_data"])
    return s


def summarise(scores: list[dict]) -> dict:
    def rate(xs):
        xs = list(xs)
        return round(sum(xs) / len(xs), 3) if xs else None

    ans = [s for s in scores if s["answerable"]]
    una = [s for s in scores if not s["answerable"]]
    by_cat = defaultdict(list)
    for s in scores:
        by_cat[s["category"]].append(s)
    return {
        "questions": len(scores), "answerable": len(ans), "unanswerable": len(una),
        "correct_answerable": sum(s["correct"] for s in ans), "accuracy": rate(s["correct"] for s in ans),
        "correct_refusals": sum(s["correct"] for s in una), "refusal_accuracy": rate(s["correct"] for s in una),
        "over_refusals": sum(s["refused"] for s in ans), "over_refusal_rate": rate(s["refused"] for s in ans),
        "route_recall": rate(s["route_recall"] for s in ans), "route_precision": rate(s["route_precision"] for s in ans if s["tables"]),
        "first_try_valid": rate(s["first_try"] for s in ans), "mean_attempts": rate(s["attempts"] for s in ans if s["attempts"]),
        "mean_seconds": rate(s["seconds"] for s in scores),
        "by_category": {c: {"n": len(v), "correct": sum(s["correct"] for s in v)} for c, v in sorted(by_cat.items())},
    }
