import json
import re
import subprocess
import sys
from pathlib import Path

import duckdb
import pandas as pd
import plotly.express as px
import streamlit as st

import pitwall as pw

st.set_page_config(page_title="Data health", layout="wide")
st.title("Data health")

ROOT = Path(__file__).resolve().parents[2]
ORDER = ["FP1", "FP2", "FP3", "SQ", "SS", "S", "Q", "R"]


@st.cache_data(ttl=60, show_spinner=False)
def load_manifest():
    """Latest record per session, and the sessions that were attempted more than once."""
    latest, attempts = {}, {}
    for line in pw.MANIFEST.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("round") is None:
            continue
        k = (r["year"], int(r["round"]), r["session"])
        latest[k] = r
        attempts[k] = attempts.get(k, 0) + 1
    dupes = {f"{k[0]} R{k[1]:02d} {k[2]}": n for k, n in attempts.items() if n > 1}
    return list(latest.values()), dupes


if not pw.MANIFEST.exists():
    st.warning("No manifest found in data/lake/_manifest yet.")
    st.stop()
records, dupes = load_manifest()


def table_bytes(r):
    return sum((t or {}).get("bytes", 0) for t in (r.get("tables") or {}).values())


def table_rows(r):
    return sum((t or {}).get("rows", 0) for t in (r.get("tables") or {}).values())


df = pd.DataFrame([{
    "year": r["year"], "round": int(r["round"]), "session": r["session"],
    "event": r.get("event", ""), "status": r.get("status", "?"),
    "telemetry": bool(r.get("with_telemetry")), "mb": table_bytes(r) / 1e6,
    "rows": table_rows(r)} for r in records])

tabs = st.tabs(["Overview", "Coverage", "Lake contents", "Quality", "Known problems",
                "Integrity", "Manifest inspector"])

with tabs[0]:
    c = st.columns(5)
    c[0].metric("Sessions", f"{len(df):,}")
    c[1].metric("Seasons", df["year"].nunique())
    c[2].metric("With telemetry", f"{int(df['telemetry'].sum()):,}")
    c[3].metric("Data", f"{df['mb'].sum():,.0f} MB")
    c[4].metric("Rows", f"{df['rows'].sum() / 1e6:,.1f} M")
    st.dataframe(df["status"].value_counts().rename("sessions").to_frame(), height=150)
    st.caption("One record per session (the latest attempt wins). Rows and megabytes are the "
               "sums over every table written for that session.")

with tabs[1]:
    grid = (df.groupby(["year", "session"]).size().unstack(fill_value=0)
            .reindex(columns=[s for s in ORDER if s in set(df["session"])], fill_value=0)
            .sort_index(ascending=False))
    fig = px.imshow(grid, text_auto=True, aspect="auto", color_continuous_scale="Blues",
                    labels=dict(x="Session type", y="Season", color="Sessions"))
    fig.update_yaxes(type="category")
    fig.update_layout(height=60 + 38 * len(grid))
    st.plotly_chart(fig)
    cov = (df.groupby("year")["telemetry"].agg(with_telemetry="sum", total="count")
           .assign(laps_only=lambda x: x["total"] - x["with_telemetry"]))
    fig2 = px.bar(cov.reset_index(), x="year", y=["with_telemetry", "laps_only"],
                  labels={"value": "Sessions", "variable": ""})
    fig2.update_xaxes(type="category")
    st.plotly_chart(fig2)
    bad = df[df["status"] != "ok"]
    if len(bad):
        st.warning(f"{len(bad)} sessions are not ok:")
        st.dataframe(bad, hide_index=True)

with tabs[2]:
    agg = {}
    for r in records:
        for name, info in (r.get("tables") or {}).items():
            if isinstance(info, dict) and "bytes" in info:
                a = agg.setdefault(name, {"table": name, "sessions": 0, "rows": 0, "bytes": 0})
                a["sessions"] += 1
                a["rows"] += info.get("rows", 0)
                a["bytes"] += info["bytes"]
    if agg:
        t = pd.DataFrame(agg.values())
        t["MB"] = (t["bytes"] / 1e6).round(1)
        t = t.drop(columns="bytes").sort_values("MB", ascending=False)
        st.subheader("Tables")
        st.dataframe(t, hide_index=True)
    by_year = df.groupby("year")["mb"].sum().round(1).reset_index()
    fig3 = px.bar(by_year, x="year", y="mb", labels={"mb": "MB"})
    fig3.update_xaxes(type="category")
    st.subheader("Size by season")
    st.plotly_chart(fig3)

    st.subheader("History (Jolpica, 1950 to now)")
    hist = pw.LAKE / "history"
    if hist.exists():
        con = duckdb.connect()
        rows_ = []
        for f in sorted(hist.glob("*.parquet")):
            n = con.sql(f"SELECT count(*) FROM read_parquet('{f}')").fetchone()[0]
            rows_.append({"table": f.stem, "rows": n, "KB": round(f.stat().st_size / 1024)})
        st.dataframe(pd.DataFrame(rows_), hide_index=True)
        res_file = hist / "results.parquet"
        if res_file.exists():
            lo, hi = con.sql(f"SELECT min(season), max(season) FROM read_parquet('{res_file}')").fetchone()
            st.caption(f"Results cover seasons {lo} to {hi}.")
        con.close()
    else:
        st.info("No history tables yet. Run python history.py.")

with tabs[3]:
    q = []
    for r in records:
        cq = r.get("car_quality")
        if isinstance(cq, dict):
            car_rows = ((r.get("tables") or {}).get("telemetry_car") or {}).get("rows") or 0
            q.append({"year": r["year"], "session": r["session"], "event": r.get("event", ""),
                      "throttle over 100 (%)": 100 * (cq.get("throttle_over_100") or 0) / car_rows
                      if car_rows else None,
                      "gear over 8": cq.get("ngear_over_8"),
                      "drs": cq.get("drs_values") or []})
    if not q:
        st.info("The manifest records do not carry car-quality metrics under the expected key "
                "(car_quality). Open the Manifest inspector to see what they do carry.")
    else:
        qd = pd.DataFrame(q)
        st.subheader("Throttle readings above 100%")
        figq = px.box(qd.dropna(subset=["throttle over 100 (%)"]), x="year",
                      y="throttle over 100 (%)", points="all", hover_data=["event", "session"])
        figq.update_xaxes(type="category")
        st.plotly_chart(figq)
        st.caption("Share of car-telemetry samples whose throttle reads above 100. The values are "
                   "stored raw and clamped for display.")
        st.subheader("DRS codes seen, by season")
        drs = (qd.groupby("year")["drs"]
               .apply(lambda s: ", ".join(str(int(v)) for v in sorted(set().union(*map(set, s)))))
               .rename("DRS codes").reset_index().sort_values("year", ascending=False))
        st.dataframe(drs, hide_index=True)
        st.caption("2026 shows only code 0 because DRS was removed; the open codes are an "
                   "interpretation of the FastF1 documentation (10, 12, 14).")
        st.subheader("Gear readings above 8")
        gear = qd.groupby("year")["gear over 8"].sum().rename("samples").reset_index()
        st.dataframe(gear.sort_values("year", ascending=False), hide_index=True)

with tabs[4]:
    @st.cache_data(ttl=120, show_spinner="Running report.py ...")
    def run_report():
        try:
            p = subprocess.run([sys.executable, str(ROOT / "report.py"), "--all"],
                               capture_output=True, text=True, timeout=120, cwd=str(ROOT))
            return p.returncode, p.stdout, p.stderr
        except Exception as e:                      # noqa: BLE001
            return -1, "", str(e)

    code_, out, err = run_report()
    if code_ != 0:
        st.error("report.py did not run from inside the app.")
        st.code((err or out)[-1500:])
    else:
        prob = re.compile(r"^\s*(\d{4}) R(\d{2}) (.+?)\s+(FP1|FP2|FP3|SQ|SS|S|Q|R)\s+(.*)$")
        rows_ = []
        for line in out.splitlines():
            m = prob.match(line)
            if not m:
                continue
            y, rd, ev, s_, txt = m.groups()
            kinds = [k for k, w in (("no circuit info", "no circuit info"),
                                    ("gap inside the lap window", "inside lap window"),
                                    ("gap outside the lap window", "outside lap window"))
                     if w in txt]
            rows_.append({"year": int(y), "round": int(rd), "event": ev, "session": s_,
                          "kind": " + ".join(kinds) or "other", "detail": txt})
        if not rows_:
            st.info("No problems listed.")
        else:
            pr = pd.DataFrame(rows_)
            st.metric("Sessions with a recorded problem", len(pr))
            figp = px.histogram(pr, x="year", color="kind")
            figp.update_xaxes(type="category")
            st.plotly_chart(figp)
            st.dataframe(pr, hide_index=True)
            st.caption("Gaps outside the lap window fall before the start or after the finish and "
                       "do not affect the lap-based pages. A gap inside the lap window (Monaco 2026 "
                       "race) breaks the race scrubber and track map for that session.")

with tabs[5]:
    st.write("verify.py re-reads every ingested file and compares its row count with the manifest.")
    if st.button("Run verify.py now"):
        with st.spinner("Checking every file against the manifest ..."):
            try:
                p = subprocess.run([sys.executable, str(ROOT / "verify.py")], capture_output=True,
                                   text=True, timeout=900, cwd=str(ROOT))
                st.code((p.stdout + p.stderr)[-3000:])
            except Exception as e:                  # noqa: BLE001
                st.error(f"Could not run verify.py: {e}")
    if dupes:
        st.subheader("Sessions attempted more than once")
        st.dataframe(pd.Series(dupes, name="attempts").rename_axis("session").reset_index(),
                     hide_index=True)
        st.caption("Re-runs after rate limits, deliberate re-ingests, or an accidental double launch "
                   "early on. The later attempt overwrote the earlier one; the manifest keeps both lines.")

with tabs[6]:
    labels = {f"{r['year']} R{int(r['round']):02d} {r['session']} {r.get('event', '')}": r
              for r in sorted(records, key=lambda x: (x["year"], int(x["round"]), x["session"]))}
    pick = st.selectbox("Session", list(labels), index=len(labels) - 1)
    st.json(labels[pick])
