#!/usr/bin/env python3
"""Trim comments in the repository's Python, TypeScript and CSS files, keeping a one or two line description per file.

    python3 tidy_comments.py            report only: what would change, nothing written
    python3 tidy_comments.py --apply    write the changes

Rules
  Python      all # comments go, except pragmas (noqa, type:, pragma, pylint, fmt:, isort, mypy, ruff, shebang, coding).
              A long docstring is cut to its first sentence (a module docstring to its first two if short);
              files that read __doc__ (command line help) keep theirs.
  TypeScript  all comments go, except the first two lines of a comment at the very top of the file and pragmas
              (@ts-, eslint, /// <reference, istanbul, c8, prettier-ignore).
  CSS         all comments go.
  Not touched SQL, YAML, shell, Dockerfiles, Markdown and JSON.

Before a file is written, the code in it is compared with the original with comments and docstrings removed
(Python: the syntax tree; TypeScript: the TypeScript compiler's own printout). A file that does not compare equal
is left alone and listed. Run from the repository root; needs git, and node with web/node_modules for TypeScript."""
import ast
import io
import json
import re
import subprocess
import sys
import tokenize
from pathlib import Path

APPLY = "--apply" in sys.argv
SKIP_DIRS = {"node_modules", ".next", "out", ".git", "__pycache__", "public", "docs", "constraints", "ci_lake", "logs", "data"}
KEEP_PY = re.compile(r"^#!|coding[:=]|noqa|type:|pragma|pylint|fmt:|isort|mypy|ruff")


def files():
    try:
        out = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True).stdout.split("\n")
    except Exception:
        out = [str(p) for p in Path(".").rglob("*") if p.is_file()]
    res = []
    for f in out:
        p = Path(f)
        if not f or set(p.parts[:-1]) & SKIP_DIRS or not p.exists():
            continue
        if p.suffix in (".py", ".ts", ".tsx", ".css") and not f.endswith((".d.ts", ".min.css")):
            res.append(f)
    return sorted(res)


# ---------------------------------------------------------------- Python

def py_strip_comments(src):
    lines = src.split("\n")
    kill, cut = set(), {}
    for t in tokenize.generate_tokens(io.StringIO(src).readline):
        if t.type == tokenize.COMMENT and not KEEP_PY.search(t.string):
            r, c = t.start
            if lines[r - 1][:c].strip() == "":
                kill.add(r - 1)
            else:
                cut[r - 1] = c
    out = []
    skip_blank = False
    for i, ln in enumerate(lines):
        if i in kill:
            skip_blank = True
            continue
        if i in cut:
            ln = ln[:cut[i]].rstrip()
        if skip_blank and ln.strip() == "" and out and out[-1].strip() == "":
            continue
        skip_blank = False
        out.append(ln)
    return "\n".join(out), len(kill) + len(cut)


def short_doc(doc, module):
    para = " ".join(doc.strip().split("\n\n")[0].split())
    if not para or "usage" in para.lower()[:12]:
        return None
    sents = re.split(r"(?<=[.!?])\s+(?=[A-Z`(\"'])", para)
    pick = sents[0]
    if module and len(sents) > 1 and len(sents[0]) + len(sents[1]) < 170:
        pick = sents[0] + " " + sents[1]
    if len(pick) > 200 or not pick.rstrip().endswith((".", "!", "?")) or "\\" in pick or '"' in pick[-1:] or '"""' in pick:
        return None
    return pick


def py_shorten_docstrings(src):
    if "__doc__" in src:
        return src, 0
    tree = ast.parse(src)
    lines = src.split("\n")
    edits = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = node.body
        if not (body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and isinstance(body[0].value.value, str)):
            continue
        st = body[0]
        doc = ast.get_docstring(node, clean=True) or ""
        if "\n" not in doc and len(doc) <= 100:
            continue
        seg_first = lines[st.lineno - 1][st.col_offset:st.col_offset + 4]
        if not seg_first.startswith(('"""', "'''")):
            continue
        new = short_doc(doc, isinstance(node, ast.Module))
        if new is None:
            continue
        edits.append((st.lineno, st.col_offset, st.end_lineno, st.end_col_offset, f'"""{new}"""'))
    for l1, c1, l2, c2, text in sorted(edits, reverse=True):
        head = lines[l1 - 1][:c1]
        tail = lines[l2 - 1][c2:]
        lines[l1 - 1:l2] = [head + text + tail]
    return "\n".join(lines), len(edits)


def py_norm(src):
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            b = node.body
            if b and isinstance(b[0], ast.Expr) and isinstance(b[0].value, ast.Constant) and isinstance(b[0].value.value, str):
                b[0].value.value = ""
    return ast.dump(tree)


def do_py(src):
    a, n = py_strip_comments(src)
    b, d = py_shorten_docstrings(a)
    if py_norm(src) != py_norm(b):
        return None, 0, 0
    return b, n, d


# ---------------------------------------------------------------- CSS

def do_css(src):
    n = len(re.findall(r"/\*[\s\S]*?\*/", src))
    out = re.sub(r"(?m)^[ \t]*/\*[\s\S]*?\*/[ \t]*\n", "", src)
    out = re.sub(r"[ \t]*/\*[\s\S]*?\*/", "", out)
    out = re.sub(r"\n{3,}", "\n\n", out).lstrip("\n")
    return out, n, 0


# ---------------------------------------------------------------- TypeScript (through the compiler)

TS_JS = r"""
const ts = require('typescript'), fs = require('fs');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const KEEP = /@ts-|eslint|\/\/\/\s*<reference|istanbul|c8 |prettier-ignore/;
const printer = ts.createPrinter({ removeComments: true });
const kindOf = (f) => (f.endsWith('x') ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
const parse = (f, t) => ts.createSourceFile(f, t, ts.ScriptTarget.Latest, true, kindOf(f));
function comments(text, sf) {
  const m = new Map();
  const add = (r) => { if (r) for (const c of r) m.set(c.pos, c); };
  (function visit(n) {
    if (n.kind === ts.SyntaxKind.JsxText) return;
    add(ts.getLeadingCommentRanges(text, n.getFullStart()));
    add(ts.getTrailingCommentRanges(text, n.getEnd()));
    ts.forEachChild(n, visit);
  })(sf);
  return [...m.values()].sort((a, b) => a.pos - b.pos);
}
const out = [];
for (const [f, text] of Object.entries(input)) {
  try {
    const sf = parse(f, text);
    const all = comments(text, sf);
    const first = sf.statements.length ? sf.statements[0].getStart() : text.length;
    const header = all.filter((c) => c.pos < first && c.kind === ts.SyntaxKind.SingleLineCommentTrivia);
    const keepAt = new Set();
    let k = 0;
    for (const c of header) {
      if (k >= 2) break;
      if (text.slice(0, c.pos).trim() === '' || keepAt.has(prevEnd(c))) { keepAt.add(c.pos); k++; }
    }
    function prevEnd(c) { let best = -1; for (const p of keepAt) { const q = all.find((x) => x.pos === p); if (q && text.slice(q.end, c.pos).trim() === '') best = p; } return best; }
    const drop = all.filter((c) => !keepAt.has(c.pos) && !KEEP.test(text.slice(c.pos, c.end)));
    let res = text;
    for (const c of drop.sort((a, b) => b.pos - a.pos)) {
      let pos = c.pos, end = c.end;
      let ls = res.lastIndexOf('\n', pos - 1) + 1;
      let le = res.indexOf('\n', end); if (le < 0) le = res.length;
      const bef = res.slice(ls, pos), aft = res.slice(end, le);
      if (bef.trimEnd().endsWith('{') && aft.trimStart().startsWith('}')) {
        pos = ls + bef.trimEnd().length - 1; end = end + (aft.length - aft.trimStart().length) + 1;
      }
      const b2 = res.slice(ls, pos), a2 = res.slice(end, le);
      if (b2.trim() === '' && a2.trim() === '') res = res.slice(0, ls) + res.slice(le + 1);
      else res = res.slice(0, pos).replace(/[ \t]+$/, '') + res.slice(end);
    }
    res = res.replace(/\n{3,}/g, '\n\n');
    const same = printer.printFile(sf) === printer.printFile(parse(f, res));
    out.push({ f, text: same ? res : null, removed: drop.length });
  } catch (e) { out.push({ f, text: null, removed: 0, error: String(e) }); }
}
process.stdout.write(JSON.stringify(out));
"""


def do_ts(batch):
    if not batch:
        return {}
    tmp = Path("web/.tidy_tmp.js")
    tmp.write_text(TS_JS)
    try:
        r = subprocess.run(["node", ".tidy_tmp.js"], cwd="web", input=json.dumps({f[4:]: s for f, s in batch.items()}),
                           capture_output=True, text=True)
    finally:
        tmp.unlink(missing_ok=True)
    if r.returncode != 0:
        sys.exit("node failed (is web/node_modules installed?):\n" + r.stderr[-600:])
    return {"web/" + o["f"]: o for o in json.loads(r.stdout)}


def main():
    todo = files()
    changed, failed, skipped = [], [], []
    ts_in = {}
    for f in todo:
        src = Path(f).read_text(encoding="utf-8")
        if f.endswith(".py"):
            try:
                new, n, d = do_py(src)
            except SyntaxError:
                new, n, d = None, 0, 0
            if new is None:
                failed.append(f)
            elif new != src:
                changed.append((f, new, n, d))
        elif f.endswith(".css"):
            new, n, d = do_css(src)
            if new != src:
                changed.append((f, new, n, d))
        else:
            if f.startswith("web/"):
                ts_in[f] = src
            else:
                skipped.append(f)
    for f, o in do_ts(ts_in).items():
        if o["text"] is None:
            failed.append(f + (" (" + o["error"][:80] + ")" if o.get("error") else ""))
        elif o["text"] != ts_in[f]:
            changed.append((f, o["text"], o["removed"], 0))
    tot_c = sum(c[2] for c in changed)
    tot_d = sum(c[3] for c in changed)
    lines_before = sum(Path(c[0]).read_text(encoding="utf-8").count("\n") for c in changed)
    lines_after = sum(c[1].count("\n") for c in changed)
    print(f"{len(changed)} files would change: {tot_c} comments removed, {tot_d} docstrings shortened, "
          f"{lines_before - lines_after} lines fewer ({lines_before} to {lines_after}).")
    for f, new, n, d in sorted(changed, key=lambda c: -c[2])[:15]:
        print(f"  {f}: {n} comments, {d} docstrings")
    if failed:
        print(f"\nLeft alone, because the code did not compare equal or the file did not parse ({len(failed)}):")
        for f in failed:
            print("  " + f)
    if not APPLY:
        print("\nNothing written. Run with --apply to write these changes.")
        return
    for f, new, n, d in changed:
        Path(f).write_text(new, encoding="utf-8")
    print("\nWritten. Now run the tests, read  git diff --stat , and commit. To undo everything:  git checkout .")


main()
