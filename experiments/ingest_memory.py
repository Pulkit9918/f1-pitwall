"""Peak memory of one real ingest. Run INSIDE the Airflow container, one session per call:
    docker compose exec -T airflow-scheduler python /opt/f1/experiments/ingest_memory.py 2025 8 R
It runs scripts/airflow_ingest.py run YEAR ROUND CODE from a throwaway folder with an empty lake and a
link to the repo's FastF1 cache, so the real lake is never touched. Prints one MEMTEST line."""
import os
import resource
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(os.environ.get("F1_REPO", "/opt/f1"))
PY = os.environ.get("F1_INGEST_PY", "/home/airflow/venvs/ingest/bin/python")


def main(year: str, rnd: str, code: str) -> int:
    with tempfile.TemporaryDirectory(prefix="memtest-") as tmp:
        data = Path(tmp) / "data"
        data.mkdir()
        link = data / "cache"
        link.symlink_to(REPO / "data" / "cache")
        try:
            start = time.time()
            rc = subprocess.run(
                [PY, str(REPO / "scripts" / "airflow_ingest.py"), "run", year, rnd, code], cwd=tmp
            ).returncode
            wall = time.time() - start
        finally:
            link.unlink()
        peak_mb = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024  # KB on Linux
        lake = data / "lake"
        written = sum(f.stat().st_size for f in lake.rglob("*") if f.is_file()) if lake.exists() else 0
    print(
        f"MEMTEST year={year} round={rnd} code={code} exit={rc} wall={wall:.0f}s "
        f"peak_memory={peak_mb:.0f}MB lake_written={written / 1e6:.0f}MB"
    )
    return rc


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit("usage: ingest_memory.py YEAR ROUND CODE")
    sys.exit(main(*sys.argv[1:]))
