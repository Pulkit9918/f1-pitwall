"use client";

import { scaleLinear } from "d3-scale";
import { line } from "d3-shape";
import { useMemo, useState } from "react";
import { REGIME_NAME, confidenceNote, pitNowAt, pitNowSeries, type AnalysisDoc } from "@/lib/analysis";
import { useWidth } from "@/lib/hooks";
import type { Point } from "@/lib/types";

const M = { l: 34, r: 14, t: 14, b: 28 };

function PitNowChart({ analysis, driver, lap, onLap }: { analysis: AnalysisDoc; driver: string; lap: number; onLap: (lap: number) => void }) {
  const [ref, width] = useWidth();
  const height = 260;
  const s = useMemo(() => pitNowSeries(analysis, driver), [analysis, driver]);
  const maxPos = Math.max(2, ...[...s.now, ...s.slow, ...s.predicted].map((p) => p.value));
  const innerW = Math.max(0, width - M.l - M.r);
  const innerH = height - M.t - M.b;
  const x = scaleLinear().domain([1, Math.max(analysis.laps, 2)]).range([0, innerW]);
  const y = scaleLinear().domain([1, maxPos]).range([0, innerH]);
  const path = line<Point>().x((p) => x(p.lap)).y((p) => y(p.value));
  const yTicks = [1, 5, 10, 15, 20].filter((t) => t <= maxPos);
  const stops = analysis.stops.filter((st) => st.driver === driver);
  // The shaded range is the fast and slow predictions drawn as a band.
  const band = s.fast.length && s.slow.length
    ? `${s.fast.map((p, i) => `${i ? "L" : "M"}${x(p.lap)},${y(p.value)}`).join("")}${[...s.slow].reverse().map((p) => `L${x(p.lap)},${y(p.value)}`).join("")}Z`
    : null;
  return (
    <div ref={ref} className="chart" style={{ minHeight: height }}>
      {width > 0 && (
        <svg
          width={width} height={height} role="img" aria-label={`Position of ${driver} by lap, and where a stop at the end of each lap would put them.`}
          onClick={(e) => {
            const r = e.currentTarget.getBoundingClientRect();
            onLap(Math.min(analysis.laps, Math.max(1, Math.round(x.invert(e.clientX - r.left - M.l)))));
          }}
        >
          <g transform={`translate(${M.l},${M.t})`}>
            {yTicks.map((t) => (
              <g key={t} transform={`translate(0,${y(t)})`}>
                <line x2={innerW} className="grid" />
                <text x={-8} dy="0.32em" textAnchor="end" className="axis-text">P{t}</text>
              </g>
            ))}
            {band && <path d={band} fill="var(--band-sc)" />}
            {stops.map((st) => <line key={st.lap} x1={x(st.lap)} x2={x(st.lap)} y1={0} y2={innerH} className="crosshair" />)}
            <path d={path(s.predicted) ?? ""} fill="none" stroke="#d95926" strokeWidth={2} strokeDasharray="5 4" />
            <path d={path(s.now) ?? ""} fill="none" stroke="#3987e5" strokeWidth={2.5} strokeLinejoin="round" />
            <line x1={x(lap)} x2={x(lap)} y1={0} y2={innerH} stroke="var(--ink)" strokeWidth={1.5} />
            {Array.from({ length: Math.floor(analysis.laps / (analysis.laps > 60 ? 10 : 5)) }, (_, i) => (i + 1) * (analysis.laps > 60 ? 10 : 5)).map((t) => (
              <text key={t} x={x(t)} y={innerH + 18} textAnchor="middle" className="axis-text">{t}</text>
            ))}
          </g>
        </svg>
      )}
      <ul className="legend">
        <li><span className="swatch" style={{ background: "#3987e5" }} /> Position</li>
        <li><span className="swatch" style={{ background: "#d95926" }} /> Predicted position after a stop at the end of that lap</li>
        <li><span className="swatch" style={{ background: "var(--band-sc)", border: "1px solid var(--ink-3)" }} /> Fast to slow range</li>
        <li>Vertical lines: stops the driver really made</li>
      </ul>
    </div>
  );
}

export function PitNowPanel({ analysis }: { analysis: AnalysisDoc }) {
  const [driver, setDriver] = useState(analysis.drivers[0] ?? "");
  const [lap, setLap] = useState(Math.min(10, Math.max(1, analysis.laps)));
  const now = pitNowAt(analysis, driver, lap);
  const note = now ? confidenceNote(now.regime, analysis.loss_ratio) : null;
  return (
    <>
      <div className="filters">
        <label className="field">
          <span className="muted small">Driver</span>
          <select value={driver} onChange={(e) => setDriver(e.target.value)}>
            {analysis.drivers.map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
        </label>
        <label className="field grow">
          <span className="muted small">Lap just finished: {lap}</span>
          <input type="range" min={1} max={Math.max(1, analysis.laps)} value={lap} onChange={(e) => setLap(Number(e.target.value))} aria-label="Lap just finished" />
        </label>
      </div>
      {now && (
        <div className="pitnow">
          <dl className="facts">
            <div><dt>Position after lap {lap}</dt><dd className="num">{now.position ?? "–"}</dd></div>
            <div><dt>If they pit now, rejoin</dt><dd className="num">{now.predicted !== null ? `P${now.predicted}` : "–"}</dd></div>
            <div><dt>Range</dt><dd className="num">{now.fast !== null && now.slow !== null ? (now.fast === now.slow ? `P${now.fast}` : `P${now.fast} to P${now.slow}`) : "–"}</dd></div>
            <div><dt>Time lost in the stop</dt><dd className="num">{now.loss !== null ? `${now.loss.toFixed(1)} s` : "–"}</dd></div>
          </dl>
          <p className="muted small">
            Track state on that lap: {REGIME_NAME[now.regime]}.{" "}
            {now.margin !== null && <>The nearest car behind is {now.margin.toFixed(1)} s from changing this answer. </>}
            {now.stopsNextLap && now.actualAfter !== null && <strong>They really did stop on lap {lap + 1} and were P{now.actualAfter} at the end of their out-lap.</strong>}
            {now.stopsNextLap && now.actualAfter === null && <strong>They really did stop on lap {lap + 1}.</strong>}
          </p>
          {note && <p className="notice-inline">{note}</p>}
        </div>
      )}
      {driver && <PitNowChart analysis={analysis} driver={driver} lap={lap} onLap={setLap} />}
      <p className="muted small">
        This is a prediction from the gaps at the end of each lap. It assumes every other car keeps its pace and does not stop in the meantime, and the
        stop costs the circuit&apos;s typical time. It is not a recommendation to pit.
      </p>
    </>
  );
}
