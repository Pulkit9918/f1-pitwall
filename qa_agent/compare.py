"""Scoring: does the agent's result table hold the reference answer?

Execution accuracy, the usual text-to-SQL measure: the two result tables are compared, not the SQL text. Column names
and the order of columns do not matter, extra columns the agent adds do not matter, row order matters only when the
question asks for it. Decimal values match within a tolerance; text ignores case and surrounding spaces.
"""
from itertools import product


def _norm(v, tol):
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return ("n", round(float(v) / tol) if tol else float(v))
    if hasattr(v, "isoformat"):
        return str(v)
    return str(v).strip().casefold()


def _key(v):
    return (0, "") if v is None else (1, repr(v))


def _col(rows, j, tol):
    return [_norm(r[j], tol) for r in rows]


def _dedupe(rows, tol):
    seen, out = set(), []
    for r in rows:
        k = tuple(repr(_norm(v, tol)) for v in r)
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def matches(ref_rows, got_rows, ordered=False, tol=0.01) -> bool:
    """True when some choice of the agent's columns reproduces every reference row.

    When the order does not matter, identical repeated rows count once: 18 returned three times is still 18."""
    if not ordered:
        ref_rows, got_rows = _dedupe(ref_rows, tol), _dedupe(got_rows, tol)
    if not ref_rows:
        return not got_rows
    if len(ref_rows) != len(got_rows):
        return False
    ncols_ref, ncols_got = len(ref_rows[0]), len(got_rows[0]) if got_rows else 0
    if ncols_got < ncols_ref:
        return False
    # decimals: compare on a grid of width tol; neighbouring grid cells are tried too, below
    ref_cols = [_col(ref_rows, j, tol) for j in range(ncols_ref)]
    got_cols = [_col(got_rows, j, tol) for j in range(ncols_got)]

    def same(a, b):
        if ordered:
            return all(_eq(x, y) for x, y in zip(a, b))
        return sorted(a, key=_key) == sorted(b, key=_key) or _loose_sorted_eq(a, b)

    candidates = [[g for g in range(ncols_got) if same(ref_cols[j], got_cols[g])] for j in range(ncols_ref)]
    if any(not c for c in candidates):
        return False
    for choice in product(*candidates):
        if len(set(choice)) < len(choice):
            continue
        ref_t = [tuple(ref_cols[j][i] for j in range(ncols_ref)) for i in range(len(ref_rows))]
        got_t = [tuple(got_cols[g][i] for g in choice) for i in range(len(got_rows))]
        if ordered:
            if all(all(_eq(a, b) for a, b in zip(x, y)) for x, y in zip(ref_t, got_t)):
                return True
        else:
            if _multiset_eq(ref_t, got_t):
                return True
    return False


def _eq(a, b):
    if isinstance(a, tuple) and isinstance(b, tuple):
        if a and a[0] == "n" and b and b[0] == "n":
            return abs(a[1] - b[1]) <= 1
        return a == b
    return a == b


def _loose_sorted_eq(a, b):
    return _multiset_eq([(x,) for x in a], [(y,) for y in b])


def _multiset_eq(a, b):
    b = list(b)
    for x in a:
        for i, y in enumerate(b):
            if all(_eq(p, q) for p, q in zip(x, y)):
                del b[i]
                break
        else:
            return False
    return not b
