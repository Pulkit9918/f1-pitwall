"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { Loading, Ready } from "@/components/State";
import {
  REGIME_NAME, byMargin, byRegime, heldOut, heldOutCost, overall, pct, places, sessionsWithStops, signedPlaces, stopRows, verdict,
  type HeldOutRow, type ScoreRow, type StopsDoc,
} from "@/lib/predictor";
import { useScore, useStops } from "@/lib/predictorData";
import "../telemetry/telemetry.css";
import "./predictor.css";

const REGIME_LABEL: Record<string, string> = { green: "Green flag", sc: "Safety car", vsc: "Virtual safety car" };

function Bar({ value, label }: { value: number | null; label: string }) {
  return (
    <span className="pbar" role="img" aria-label={label}>
      <span className="pbar-fill" style={{ width: `${Math.max(0, Math.min(1, value ?? 0)) * 100}%` }} />
      <span className="pbar-text num">{pct(value)}</span>
    </span>
  );
}

function Headline({ rows, scope }: { rows: ScoreRow[]; scope: ScoreRow["scope"] }) {
  const o = overall(rows, scope);
  if (!o) return <p className="muted">No stops were scored.</p>;
  return (
    <>
      <p className="lede">
        Across <strong>{o.stops.toLocaleString()}</strong> {scope === "all" ? "pit stops" : "undisturbed pit stops"}, the prediction named the exact place the driver
        came out in <strong>{pct(o.hit)}</strong> of the time, and was within one place <strong>{pct(o.within_one)}</strong> of the time.
        Keeping the place held before the stop would have been right <strong>{pct(o.no_loss_hit)}</strong> of the time.
      </p>
      <div className="table-wrap">
        <table className="narrow">
          <caption className="sr-only">Accuracy of the prediction and of two simpler guesses</caption>
          <thead>
            <tr><th scope="col">Method</th><th scope="col" className="num">Exact place</th><th scope="col" className="num">Average miss, in places</th></tr>
          </thead>
          <tbody>
            <tr><th scope="row">Pit-now prediction (the circuit&apos;s own pit loss)</th><td className="num">{pct(o.hit)}</td><td className="num">{places(o.mae)}</td></tr>
            <tr><th scope="row">Same method, one pit loss for every circuit</th><td className="num">{pct(o.global_hit)}</td><td className="num">{places(o.global_mae)}</td></tr>
            <tr><th scope="row">No loss: keep the place held before the stop</th><td className="num">{pct(o.no_loss_hit)}</td><td className="num">{places(o.no_loss_mae)}</td></tr>
          </tbody>
        </table>
      </div>
      <p className="axis-caption">
        {o.bias != null && Math.abs(o.bias) >= 0.005
          ? `On average the predicted place is ${Math.abs(o.bias).toFixed(2)} places ${o.bias > 0 ? "worse" : "better"} than the place the driver got (${signedPlaces(o.bias)}, predicted minus actual). `
          : "On average the predicted place matches the place the driver got. "}
        The real place fell inside the prediction&apos;s own fast-to-slow range {pct(o.in_range)} of the time.
        {!o.reliable && " This is under 30 stops, so treat it as indicative only."}
      </p>
    </>
  );
}

function HeldOutTable({ rows, scope }: { rows: HeldOutRow[]; scope: ScoreRow["scope"] }) {
  const h = heldOut(rows, scope);
  if (!h) return null;
  const cost = heldOutCost(h);
  return (
    <>
      <div className="table-wrap">
        <table className="narrow">
          <caption className="sr-only">The same green-flag stops, scored with the pit loss estimated with and without the race itself</caption>
          <thead><tr><th scope="col">Pit loss estimated</th><th scope="col" className="num">Exact place</th><th scope="col" className="num">Average miss, in places</th></tr></thead>
          <tbody>
            <tr><th scope="row">From every race, including the one scored</th><td className="num">{pct(h.in_sample_hit)}</td><td className="num">{places(h.in_sample_mae)}</td></tr>
            <tr><th scope="row">From the other races only</th><td className="num">{pct(h.held_out_hit)}</td><td className="num">{places(h.held_out_mae)}</td></tr>
          </tbody>
        </table>
      </div>
      <p className="axis-caption">
        {h.stops.toLocaleString()} green-flag stops. Leaving the scored race out of the pit-loss estimate{" "}
        {cost == null ? "changes the hit rate by an unknown amount" : Math.abs(cost) < 0.05 ? "does not change the hit rate" : cost > 0 ? `costs ${cost.toFixed(1)} points of hit rate` : `raises the hit rate by ${(-cost).toFixed(1)} points`}
        {h.loss_shift_s != null && `, and moves the assumed loss by ${Math.abs(h.loss_shift_s).toFixed(2)} s on average`}. {pct(h.circuit_share)} of these stops used the circuit&apos;s other races; the rest fell back to the all-circuit figure because the circuit had too few.
      </p>
    </>
  );
}

function RegimeTable({ rows, scope }: { rows: ScoreRow[]; scope: ScoreRow["scope"] }) {
  const list = byRegime(rows, scope);
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr><th scope="col">Track state before the stop</th><th scope="col" className="num">Stops</th><th scope="col" className="num">Exact place</th><th scope="col" className="num">Within one</th><th scope="col" className="num">Average miss</th><th scope="col" className="num">In range</th><th scope="col" className="num">Beats no-loss guess by</th></tr>
        </thead>
        <tbody>
          {list.map((r) => (
            <tr key={r.regime} className={r.reliable ? undefined : "faint"}>
              <th scope="row">{REGIME_LABEL[r.regime] ?? r.regime}{!r.reliable && <span className="muted small"> (few stops)</span>}</th>
              <td className="num">{r.stops.toLocaleString()}</td><td className="num">{pct(r.hit)}</td><td className="num">{pct(r.within_one)}</td>
              <td className="num">{places(r.mae)}</td><td className="num">{pct(r.in_range)}</td>
              <td className="num">{r.mae != null && r.no_loss_mae != null ? `${(r.no_loss_mae - r.mae).toFixed(2)} places` : "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MarginTable({ rows, scope }: { rows: ScoreRow[]; scope: ScoreRow["scope"] }) {
  const list = byMargin(rows, scope);
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr><th scope="col">Margin</th><th scope="col" className="num">Stops</th><th scope="col">Exact place</th><th scope="col">Within one place</th></tr>
        </thead>
        <tbody>
          {list.map((r) => (
            <tr key={r.margin} className={r.reliable ? undefined : "faint"}>
              <th scope="row">{r.margin === "no margin" ? "No car to compare with" : r.margin}</th>
              <td className="num">{r.stops.toLocaleString()}</td>
              <td><Bar value={r.hit} label={`Exact place ${pct(r.hit)} for margin ${r.margin}`} /></td>
              <td><Bar value={r.within_one} label={`Within one place ${pct(r.within_one)} for margin ${r.margin}`} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Browse({ doc }: { doc: StopsDoc }) {
  const sessions = useMemo(() => sessionsWithStops(doc), [doc]);
  const [chosen, setChosen] = useState<number>(() => sessions[sessions.length - 1]?.index ?? 0);
  const rows = useMemo(() => stopRows(doc, chosen), [doc, chosen]);
  const meta = doc.sessions[chosen];
  return (
    <>
      <label className="field browse-pick">
        <span>Race</span>
        <select value={chosen} onChange={(e) => setChosen(Number(e.target.value))}>
          {[...sessions].reverse().map(({ index, count }) => (
            <option key={index} value={index}>{doc.sessions[index].year} round {doc.sessions[index].round}, {doc.sessions[index].event ?? doc.sessions[index].key} ({count} stops)</option>
          ))}
        </select>
      </label>
      {meta && <p className="muted small"><Link href={`/race?key=${encodeURIComponent(meta.key)}`}>Open this race&apos;s analysis</Link></p>}
      <div className="table-wrap">
        <table className="stop-table">
          <thead>
            <tr>
              <th scope="col">Driver</th><th scope="col" className="num">Stop lap</th><th scope="col">Track</th><th scope="col" className="num">Before</th>
              <th scope="col" className="num">Predicted</th><th scope="col" className="num">Range</th><th scope="col" className="num">Actual</th><th scope="col">Result</th><th scope="col" className="num">Margin</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <th scope="row">{r.driver}</th><td className="num">{r.lap}</td><td>{REGIME_NAME[r.regime] ?? r.regime}</td><td className="num">{r.before}</td>
                <td className="num">{r.predicted}</td><td className="num">{r.fast === r.slow ? r.fast : `${r.fast} to ${r.slow}`}</td><td className="num">{r.actual}</td>
                <td><span className={`verdict verdict-${verdict(r).replace(" ", "-")}`}>{verdict(r)}</span>{r.disturbed && <span className="muted small"> others stopped nearby</span>}</td>
                <td className="num">{r.margin == null ? "-" : `${r.margin.toFixed(1)} s`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

export default function PredictorPage() {
  const score = useScore();
  const stops = useStops();
  const [scope, setScope] = useState<ScoreRow["scope"]>("all");
  return (
    <>
      <section className="hero hero-small">
        <h1>Pit-stop prediction, checked against real stops</h1>
        <p className="lede">
          On the race analysis pages, &quot;pit now&quot; predicts where a driver would rejoin if they stopped at the end of the lap. Here every real stop in the data is
          scored against that prediction: it is the one made on the lap before the stop, and the outcome is the driver&apos;s position at the end of the out-lap.
        </p>
      </section>

      <Ready load={score} label="Loading the scores">
        {(doc) => (
          <>
            <div className="chips" role="group" aria-label="Which stops to score">
              <button type="button" className={`chip${scope === "all" ? " chip-on" : ""}`} aria-pressed={scope === "all"} onClick={() => setScope("all")}>All stops</button>
              <button type="button" className={`chip${scope === "undisturbed" ? " chip-on" : ""}`} aria-pressed={scope === "undisturbed"} onClick={() => setScope("undisturbed")}>Stops nobody else pitted near</button>
            </div>
            <p className="muted small">
              The prediction assumes every other car stays out and keeps its pace. {scope === "all" ? "These figures include stops where other cars pitted close by, which the prediction cannot know about." : "These stops had no other driver pitting from the lap before to the out-lap, so they test the pit-loss figure by itself."}
            </p>
            <section aria-labelledby="headline"><h2 id="headline">How often it was right</h2><Headline rows={doc.rows} scope={scope} /></section>
            <section aria-labelledby="heldout"><h2 id="heldout">Is it just remembering the answers?</h2>
              <p className="muted small">The pit loss is estimated from the same races the prediction is scored on. This repeats the green-flag stops with each race left out of its own estimate.</p>
              <HeldOutTable rows={doc.heldout ?? []} scope={scope} /></section>
            <section aria-labelledby="regime"><h2 id="regime">By track state</h2><RegimeTable rows={doc.rows} scope={scope} />
              <p className="axis-caption">Rows with fewer than 30 stops are faded.</p>
              {byRegime(doc.rows, scope).filter((r) => r.mae != null && r.no_loss_mae != null && r.mae > r.no_loss_mae).map((r) => (
                <p key={r.regime} className="notice-inline">
                  Under {REGIME_LABEL[r.regime]?.toLowerCase() ?? r.regime} the prediction did worse than simply keeping the place held before the stop
                  (average miss {places(r.mae)} places against {places(r.no_loss_mae)}). Cars bunch up and many stop at once, so the field changes in ways the prediction does not model.
                </p>
              ))}
            </section>
            <section aria-labelledby="margin"><h2 id="margin">Does the margin tell you when to trust it?</h2><MarginTable rows={doc.rows} scope={scope} />
              <p className="axis-caption">The margin is how many seconds of pit loss separated the prediction from the next place changing. If it is a useful warning, predictions with a small margin should be right less often than ones with a large margin.</p></section>
          </>
        )}
      </Ready>

      <section aria-labelledby="browse">
        <h2 id="browse">Every stop in a race</h2>
        {stops.state === "loading" ? <Loading label="Loading the stops" /> : <Ready load={stops}>{(doc) => <Browse doc={doc} />}</Ready>}
      </section>

      <section aria-labelledby="notes">
        <h2 id="notes">What this does and does not show</h2>
        <ul className="notes">
          <li>The headline figures use a pit loss estimated from all races, including the one being scored. The held-out table above repeats the green-flag stops without that, and is the fairer number. Safety car and virtual safety car stops are not held out, because their ratios are estimated across all races.</li>
          <li>The outcome is the position at the end of the out-lap. Cars that retire or are lapped out of the data are left out, and so are stops under a red flag, where no prediction is made.</li>
          <li>Other drivers&apos; stops move the order, and the prediction assumes they do not. The &quot;nobody else pitted near&quot; view removes those stops.</li>
          <li>Race strategy decisions depend on tyre life, traffic and the rest of the race. This only checks one thing: whether the place after the stop was predicted correctly.</li>
        </ul>
      </section>
    </>
  );
}
