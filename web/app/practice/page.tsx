"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo } from "react";
import { CompoundChip } from "@/components/CompoundChip";
import { Loading, LoadError, Ready } from "@/components/State";
import { StrategyChart } from "@/components/StrategyChart";
import { COMPOUND_COLOR } from "@/lib/colors";
import { useSession, useSessions } from "@/lib/data";
import { fmtDeg, fmtLap, isPractice, sessionLabel } from "@/lib/format";
import { LONG_RUN_MIN_CLEAN, fastestLaps, longRuns, runSummary } from "@/lib/practice";
import type { SessionDoc } from "@/lib/types";
import "./practice.css";

function Practice({ doc }: { doc: SessionDoc }) {
  const fast = useMemo(() => fastestLaps(doc), [doc]);
  const runs = useMemo(() => longRuns(doc), [doc]);
  const s = doc.session;
  return (
    <>
      <section className="hero hero-small">
        <p className="crumb"><Link href="/practice">Practice</Link></p>
        <h1>{s.event}, {s.year}</h1>
        <p className="lede">{sessionLabel(s.session_code, s.session_name)}, round {s.round}. {[s.circuit_name, s.country].filter(Boolean).join(", ")}</p>
        <p className="muted small">
          <Link href={`/race?key=${encodeURIComponent(s.session_key)}`}>Full session analysis</Link> · <Link href={`/compare?key=${encodeURIComponent(s.session_key)}`}>Compare two drivers</Link>
        </p>
      </section>

      <section aria-labelledby="fast">
        <h2 id="fast">Fastest laps</h2>
        {fast.length === 0 ? <p className="muted">No timed laps in this session.</p> : (
          <div className="table-wrap">
            <table className="narrow">
              <thead><tr><th scope="col" className="num">#</th><th scope="col">Driver</th><th scope="col" className="num">Best lap</th><th scope="col" className="num">Gap</th><th scope="col">Tyre</th><th scope="col" className="num">Lap</th><th scope="col" className="num">Timed laps</th><th scope="col" className="num">Runs</th></tr></thead>
              <tbody>
                {fast.map((r, i) => {
                  const sum = runSummary(doc, r.driver);
                  return (
                    <tr key={r.driver}>
                      <td className="num">{i + 1}</td><th scope="row">{r.driver}</th><td className="num">{fmtLap(r.time)}</td>
                      <td className="num">{i === 0 ? "" : `+${r.gap.toFixed(3)}`}</td>
                      <td><CompoundChip compound={r.compound} /> <span className="muted small">{r.tyreAge != null ? `${r.tyreAge} laps old` : ""}</span></td>
                      <td className="num">{r.lap}</td><td className="num">{r.laps}</td><td className="num">{sum.runs}{sum.longRuns > 0 && <span className="muted small"> ({sum.longRuns} long)</span>}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        <p className="axis-caption">A driver&apos;s quickest timed lap that was not deleted. Practice laps are run with different fuel loads and engine modes, so a best lap is not a measure of true pace.</p>
      </section>

      <section aria-labelledby="runs">
        <h2 id="runs">Long runs</h2>
        <p className="muted small">Runs with at least {LONG_RUN_MIN_CLEAN} clean laps, which is the closest practice gets to race pace. Pace is the median clean lap, compared within a compound only.</p>
        {runs.length === 0 && <p className="muted">No driver completed a run of {LONG_RUN_MIN_CLEAN} clean laps in this session.</p>}
        {runs.map(({ compound, runs: list }) => {
          const worst = Math.max(0.001, ...list.map((r) => r.gap));
          return (
            <div key={compound} className="run-group">
              <h3><CompoundChip compound={compound} /> {compound.charAt(0) + compound.slice(1).toLowerCase()}</h3>
              <div className="table-wrap">
                <table className="narrow">
                  <thead><tr><th scope="col">Driver</th><th scope="col" className="num">Laps</th><th scope="col" className="num">Clean</th><th scope="col" className="num">Median lap</th><th scope="col">Behind the quickest</th><th scope="col" className="num">Tyre wear</th></tr></thead>
                  <tbody>
                    {list.map((r) => (
                      <tr key={`${r.driver}-${r.startLap}`}>
                        <th scope="row">{r.driver}</th><td className="num" title={`laps ${r.startLap} to ${r.endLap}`}>{r.laps}</td><td className="num">{r.cleanLaps}</td><td className="num">{fmtLap(r.pace)}</td>
                        <td><span className="gapbar"><span className="gapbar-fill" style={{ width: `${(r.gap / worst) * 100}%`, background: COMPOUND_COLOR[compound] ?? "var(--ink-3)" }} /><span className="num gapbar-text">{r.gap === 0 ? "quickest" : `+${r.gap.toFixed(3)}`}</span></span></td>
                        <td className="num">{fmtDeg(r.degradation)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          );
        })}
        <p className="axis-caption">Tyre wear is the slope of lap time against tyre age over the run, fuel burn included, so it understates how much the tyre itself is losing. A driver can appear in a group more than once, once for each long run.</p>
      </section>

      <section aria-labelledby="timeline">
        <h2 id="timeline">Every run</h2>
        <StrategyChart doc={doc} compact />
      </section>
    </>
  );
}

function PracticeList() {
  const load = useSessions();
  return (
    <>
      <section className="hero hero-small">
        <h1>Practice sessions</h1>
        <p className="lede">Fastest laps and long-run pace for every practice session, with who ran what and for how long.</p>
      </section>
      <Ready load={load} label="Loading sessions">
        {({ sessions }) => {
          const list = sessions.filter((x) => isPractice(x.session_code) && x.has_laps);
          const years = [...new Set(list.map((x) => x.year))].sort((a, b) => b - a);
          return (
            <>
              {years.map((y) => (
                <section key={y} aria-labelledby={`y${y}`}>
                  <h2 id={`y${y}`}>{y}</h2>
                  <ul className="session-links">
                    {list.filter((x) => x.year === y).sort((a, b) => a.round - b.round || a.session_code.localeCompare(b.session_code)).map((x) => (
                      <li key={x.session_key}><Link href={`/practice?key=${encodeURIComponent(x.session_key)}`}>{x.event}, {sessionLabel(x.session_code, x.session_name)}</Link></li>
                    ))}
                  </ul>
                </section>
              ))}
              {list.length === 0 && <p className="muted">No practice sessions with laps.</p>}
            </>
          );
        }}
      </Ready>
    </>
  );
}

function PracticeInner() {
  const key = useSearchParams().get("key");
  const doc = useSession(key);
  if (!key) return <PracticeList />;
  if (doc.state === "error") return <LoadError message={doc.message} />;
  if (doc.state === "loading") return <Loading label="Loading the session" />;
  return <Practice key={key} doc={doc.data} />;
}

export default function PracticePage() {
  return (
    <Suspense fallback={<Loading />}>
      <PracticeInner />
    </Suspense>
  );
}
