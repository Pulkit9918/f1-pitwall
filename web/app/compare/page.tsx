"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { CompoundChip } from "@/components/CompoundChip";
import { LapDeltaChart } from "@/components/LapDeltaChart";
import { SectorTime } from "@/components/SectorTime";
import { SessionPicker } from "@/components/SessionPicker";
import { Loading, LoadError, Ready } from "@/components/State";
import { DRIVER_COLORS } from "@/lib/colors";
import { fmtLap, sessionLabel } from "@/lib/format";
import { driversByBest, isRaceLike, lapRows, pairedLaps, summarise, type LapDoc, type LapRow, type Summary } from "@/lib/laps";
import { useLapDoc, useLapIndex } from "@/lib/lapData";
import { statusNote } from "@/lib/traces";
import "../telemetry/telemetry.css";
import "./compare.css";

const sec = (v: number | null) => (v == null ? "-" : v.toFixed(3));
function gap(a: number | null, b: number | null, an: string, bn: string): string {
  if (a == null || b == null) return "-";
  const d = a - b;
  if (Math.abs(d) < 0.0005) return "level";
  return `${d < 0 ? an : bn} ${Math.abs(d).toFixed(3)} s quicker`;
}

function Metric({ label, a, b, an, bn, fmt = sec, note }: { label: string; a: number | null; b: number | null; an: string; bn: string; fmt?: (v: number | null) => string; note?: string }) {
  return (
    <tr>
      <th scope="row">{label}{note && <span className="muted small"> {note}</span>}</th>
      <td className="num">{fmt(a)}</td>
      <td className="num">{fmt(b)}</td>
      <td className="muted">{gap(a, b, an, bn)}</td>
    </tr>
  );
}

function SummaryTable({ a, b, sa, sb }: { a: string; b: string; sa: Summary; sb: Summary }) {
  const count = (v: number | null) => (v == null ? "-" : String(v));
  return (
    <div className="table-wrap">
      <table className="narrow compare-summary">
        <thead>
          <tr>
            <th scope="col"><span className="sr-only">Measure</span></th>
            <th scope="col" className="num"><span className="swatch" style={{ background: DRIVER_COLORS[0] }} /> {a}</th>
            <th scope="col" className="num"><span className="swatch" style={{ background: DRIVER_COLORS[1] }} /> {b}</th>
            <th scope="col">Difference</th>
          </tr>
        </thead>
        <tbody>
          <Metric label="Best lap" a={sa.best} b={sb.best} an={a} bn={b} fmt={fmtLap} />
          <Metric label="Best sector 1" a={sa.bestSectors[0]} b={sb.bestSectors[0]} an={a} bn={b} />
          <Metric label="Best sector 2" a={sa.bestSectors[1]} b={sb.bestSectors[1]} an={a} bn={b} />
          <Metric label="Best sector 3" a={sa.bestSectors[2]} b={sb.bestSectors[2]} an={a} bn={b} />
          <Metric label="Best sectors added up" note="(not necessarily a lap anyone drove)" a={sa.theoretical} b={sb.theoretical} an={a} bn={b} fmt={fmtLap} />
          <Metric label="Typical clean lap" note="(median)" a={sa.medianClean} b={sb.medianClean} an={a} bn={b} fmt={fmtLap} />
          <Metric label="Typical clean sector 1" a={sa.medianCleanSectors[0]} b={sb.medianCleanSectors[0]} an={a} bn={b} />
          <Metric label="Typical clean sector 2" a={sa.medianCleanSectors[1]} b={sb.medianCleanSectors[1]} an={a} bn={b} />
          <Metric label="Typical clean sector 3" a={sa.medianCleanSectors[2]} b={sb.medianCleanSectors[2]} an={a} bn={b} />
          <tr><th scope="row">Purple sectors set</th><td className="num">{sa.purple}</td><td className="num">{sb.purple}</td><td className="muted">fastest in the session at the time</td></tr>
          <tr><th scope="row">Timed laps</th><td className="num">{count(sa.laps)}</td><td className="num">{count(sb.laps)}</td><td className="muted">{sa.clean} and {sb.clean} clean</td></tr>
        </tbody>
      </table>
    </div>
  );
}

function LapCells({ r }: { r: LapRow | undefined }) {
  if (!r) return <><td colSpan={5} className="muted lap-missing">no lap</td></>;
  return (
    <>
      {r.sectors.map((s, k) => <td key={k}><SectorTime value={s} colour={r.colours[k]} /></td>)}
      <td className="num lap-total">{r.deleted ? <span title="Time deleted">deleted</span> : fmtLap(r.time)}</td>
      <td className="lap-tyre"><CompoundChip compound={r.compound} /> <span className="muted small">{r.age != null ? r.age : ""}{r.pit ? " pit" : ""}{statusNote(r.status ?? undefined) ? ` ${statusNote(r.status ?? undefined)}` : ""}</span></td>
    </>
  );
}

function LapTable({ a, b, ra, rb, race }: { a: string; b: string; ra: LapRow[]; rb: LapRow[]; race: boolean }) {
  const [all, setAll] = useState(false);
  const numbers = useMemo(() => [...new Set([...ra, ...rb].map((r) => r.n))].sort((x, y) => x - y), [ra, rb]);
  const byA = useMemo(() => new Map(ra.map((r) => [r.n, r])), [ra]);
  const byB = useMemo(() => new Map(rb.map((r) => [r.n, r])), [rb]);
  const shown = all ? numbers : numbers.slice(0, 25);
  return (
    <>
      <div className="table-wrap">
        <table className="lap-table">
          <thead>
            <tr>
              <th rowSpan={2} scope="col">Lap</th>
              <th colSpan={5} scope="colgroup"><span className="swatch" style={{ background: DRIVER_COLORS[0] }} /> {a}</th>
              <th colSpan={5} scope="colgroup"><span className="swatch" style={{ background: DRIVER_COLORS[1] }} /> {b}</th>
              {race && <th rowSpan={2} scope="col" className="num">{a} minus {b}</th>}
            </tr>
            <tr>
              {["S1", "S2", "S3", "Lap", "Tyre"].map((h) => <th key={`a${h}`} scope="col">{h}</th>)}
              {["S1", "S2", "S3", "Lap", "Tyre"].map((h) => <th key={`b${h}`} scope="col">{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {shown.map((n) => {
              const x = byA.get(n), y = byB.get(n);
              const d = race && x?.time != null && y?.time != null && !x.deleted && !y.deleted ? x.time - y.time : null;
              return (
                <tr key={n}>
                  <th scope="row" className="num">{n}</th>
                  <LapCells r={x} />
                  <LapCells r={y} />
                  {race && <td className="num">{d == null ? "-" : `${d > 0 ? "+" : d < 0 ? "-" : ""}${Math.abs(d).toFixed(3)}`}</td>}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {numbers.length > 25 && (
        <button type="button" className="link-button" onClick={() => setAll(!all)}>{all ? "Show the first 25 laps" : `Show all ${numbers.length} laps`}</button>
      )}
    </>
  );
}

function Compare({ doc }: { doc: LapDoc }) {
  const order = useMemo(() => driversByBest(doc), [doc]);
  const [a, setA] = useState(order[0] ?? "");
  const [b, setB] = useState(order[1] ?? order[0] ?? "");
  const rows = useMemo(() => Object.fromEntries(doc.drivers.map((d) => [d.code, lapRows(d)])), [doc]);
  const ra = rows[a] ?? [], rb = rows[b] ?? [];
  const sa = useMemo(() => summarise(ra), [ra]);
  const sb = useMemo(() => summarise(rb), [rb]);
  const race = isRaceLike(doc.session_code);
  const pairs = useMemo(() => (race ? pairedLaps(ra, rb) : []), [race, ra, rb]);
  const same = a === b;
  const option = (code: string) => <option key={code} value={code}>{code}{doc.drivers.find((d) => d.code === code)?.team ? `, ${doc.drivers.find((d) => d.code === code)?.team}` : ""}</option>;

  return (
    <>
      <section className="hero hero-small">
        <p className="crumb"><Link href="/compare">Drivers</Link></p>
        <h1>{doc.event}, {doc.year}</h1>
        <p className="lede">{sessionLabel(doc.session_code)}, round {doc.round}. {doc.circuit_name ?? ""}</p>
        <p className="muted small">
          <Link href={`/race?key=${encodeURIComponent(doc.session_key)}`}>Session analysis</Link>
          {race && <> · <Link href={`/telemetry?key=${encodeURIComponent(doc.session_key)}`}>Compare laps against distance</Link></>}
        </p>
      </section>

      <section aria-labelledby="pick">
        <h2 id="pick">Two drivers</h2>
        <div className="lap-add">
          <label className="field"><span>First driver</span>
            <select value={a} onChange={(e) => setA(e.target.value)}>{doc.drivers.map((d) => option(d.code))}</select></label>
          <label className="field"><span>Second driver</span>
            <select value={b} onChange={(e) => setB(e.target.value)}>{doc.drivers.map((d) => option(d.code))}</select></label>
          <button type="button" className="btn btn-quiet" onClick={() => { setA(b); setB(a); }}>Swap</button>
        </div>
        {same && <p className="notice-inline">Pick two different drivers to compare them.</p>}
      </section>

      {!same && (
        <>
          <section aria-labelledby="summary">
            <h2 id="summary">Pace</h2>
            <SummaryTable a={a} b={b} sa={sa} sb={sb} />
            <p className="axis-caption">
              Best sectors and the best lap use every timed lap that was not deleted. Typical values use clean laps only, so they
              are less affected by traffic, pit laps and neutralised laps. The difference column names the driver who was quicker.
            </p>
          </section>

          {race && (
            <section aria-labelledby="delta">
              <h2 id="delta">Lap by lap</h2>
              <LapDeltaChart pairs={pairs} a={a} b={b} />
            </section>
          )}

          <section aria-labelledby="laps">
            <h2 id="laps">Every lap</h2>
            <ul className="legend sector-legend" aria-label="Sector colours">
              <li><span className="swatch" style={{ background: "var(--sector-purple)" }} />Fastest of anyone in the session so far</li>
              <li><span className="swatch" style={{ background: "var(--sector-green)" }} />Driver&apos;s own best so far</li>
              <li><span className="swatch" style={{ background: "var(--sector-yellow)" }} />Slower than the driver&apos;s best</li>
            </ul>
            <LapTable a={a} b={b} ra={ra} rb={rb} race={race} />
            {!race && <p className="axis-caption">Laps are lined up by lap number only; in qualifying and practice the drivers run at different times, so no lap-by-lap difference is shown.</p>}
          </section>
        </>
      )}
    </>
  );
}

function SessionList() {
  const load = useLapIndex();
  return (
    <>
      <section className="hero hero-small">
        <h1>Driver comparison</h1>
        <p className="lede">Choose a session, then compare any two drivers: best lap, sector times with purple, green and yellow, typical pace, and every lap side by side.</p>
      </section>
      <Ready load={load} label="Loading sessions">
        {(idx) => <SessionPicker sessions={idx.sessions} base="/compare" empty="No laps exported yet. Run python scripts/export_laps.py." />}
      </Ready>
    </>
  );
}

function CompareInner() {
  const key = useSearchParams().get("key");
  const doc = useLapDoc(key);
  if (!key) return <SessionList />;
  if (doc.state === "error" && doc.message.startsWith("404")) {
    return (
      <section className="hero hero-small">
        <h1>No laps for this session</h1>
        <p className="lede"><Link href="/compare">Choose another session</Link>.</p>
      </section>
    );
  }
  if (doc.state === "error") return <LoadError message={doc.message} />;
  if (doc.state === "loading") return <Loading label="Loading the laps" />;
  return <Compare key={doc.data.session_key} doc={doc.data} />;
}

export default function ComparePage() {
  return (
    <Suspense fallback={<Loading />}>
      <CompareInner />
    </Suspense>
  );
}
