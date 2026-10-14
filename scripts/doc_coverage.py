"""Documentation coverage of the dbt project, from dbt's own artifacts. Run from the repo root after
   ~/.venvs/f1-dbt/bin/dbt docs generate --project-dir dbt --profiles-dir dbt
Usage:  python scripts/doc_coverage.py            # report: every model and its undocumented columns
        python scripts/doc_coverage.py --check    # exit 1 if any model, or any column of a gold model, has no description
Uses only the standard library."""
import json
import sys
from pathlib import Path

target = Path("dbt/target")
manifest = json.loads((target / "manifest.json").read_text())
catalog_file = target / "catalog.json"
catalog = json.loads(catalog_file.read_text())["nodes"] if catalog_file.exists() else {}

models = sorted((n for n in manifest["nodes"].values() if n["resource_type"] == "model"),
                key=lambda n: (n.get("schema", ""), n["name"]))
no_model_doc, col_total, col_doc, gold_missing = [], 0, 0, 0
for n in models:
    cols = catalog.get(n["unique_id"], {}).get("columns", {})
    names = {c.lower(): c for c in cols} | {c.lower(): c for c in n.get("columns", {})}
    missing = []
    for low, name in names.items():
        meta = {k.lower(): v for k, v in n.get("columns", {}).items()}.get(low, {})
        col_total += 1
        if (meta.get("description") or "").strip():
            col_doc += 1
        else:
            ctype = {k.lower(): v for k, v in cols.items()}.get(low, {}).get("type", "?")
            missing.append(f"{name} {ctype}")
    has_desc = bool((n.get("description") or "").strip())
    if not has_desc:
        no_model_doc.append(n["name"])
    if n.get("schema") == "gold":
        gold_missing += len(missing)
    print(f"== {n.get('schema')}.{n['name']}  [{n['config'].get('materialized')}]  model description: "
          f"{'yes' if has_desc else 'NO'}  columns undocumented: {len(missing)}/{len(names)}")
    if missing:
        print("   " + ", ".join(missing))
print(f"\nmodels: {len(models)}; without a description: {len(no_model_doc)} {no_model_doc}")
print(f"columns: {col_doc}/{col_total} documented ({100 * col_doc / max(col_total, 1):.0f}%)")
if "--check" in sys.argv and (no_model_doc or gold_missing):
    print(f"CHECK FAILED: {len(no_model_doc)} models and {gold_missing} gold columns undocumented")
    sys.exit(1)
