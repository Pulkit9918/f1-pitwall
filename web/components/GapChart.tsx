"use client";

import { scaleLinear } from "d3-scale";
import { line } from "d3-shape";
import { useMemo, useState } from "react";
import { DRIVER_COLORS } from "@/lib/colors";
import { useWidth } from "@/lib/hooks";
import { gapSeries, type AnalysisDoc, type GapMetric } from "@/lib/analysis";
import { maxLap, periodBands } from "@/lib/race";
import type { Point, SessionDoc } from "@/lib/types";
import { Tip } from "./Tip";

const M = { l: 44, r: 40, t: 22, b: 28 };

export function GapChart({ doc, analysis, slots, metric }: { doc: SessionDoc; analysis: AnalysisDoc; slots: (string | null)[]; metric: GapMetric }) {
  const [ref, width] = useWidth();
  const [hover, setHover] = useState<{ lap: number; x: number; y: number } | null>(null);
  const height = 320;
  const laps = Math.max(maxLap(doc), analysis.laps, 1);
  const bands = useMemo(() => periodBands(doc), [doc]);
  const selected = slots.flatMap((code, slot) => (code ? [{ code, slot, pts: gapSeries(analysis, code, metric) }] : []));
  // The axis fits the selected drivers only: a lapped car's gap is longer than a lap and would flatten everyone else.
  const top = Math.max(5, ...selected.flatMap((s) => s.pts.map((p) => p.value)));
  const innerW = Math.max(0, width - M.l - M.r);
  const innerH = height - M.t - M.b;
  const x = scaleLinear().domain([0, laps]).range([0, innerW]);
  const y = scaleLinear().domain([0, top]).nice().range([0, innerH]);
  const path = line<Point>().x((p) => x(p.lap - 0.5)).y((p) => y(p.value));
  const yTicks = y.ticks(5);
  const tickStep = laps > 60 ? 10 : 5;
  const xTicks = Array.from({ length: Math.floor(laps / tickStep) }, (_, i) => (i + 1) * tickStep);
  const at = (code: string, lap: number) => selected.find((s) => s.code === code)?.pts.find((p) => p.lap === lap);

  return (
    <div ref={ref} className="chart" style={{ minHeight: height }}>
      {width > 0 && (
        <svg
          width={width} height={height} role="img"
          aria-label={metric === "leader" ? "Gap to the race leader at the end of each lap." : "Interval to the car ahead at the end of each lap."}
          onMouseLeave={() => setHover(null)}
          onMouseMove={(e) => {
            const r = e.currentTarget.getBoundingClientRect();
            const lap = Math.min(laps, Math.max(1, Math.round(x.invert(e.clientX - r.left - M.l) + 0.5)));
            setHover({ lap, x: e.clientX - r.left, y: e.clientY - r.top });
          }}
        >
          <g transform={`translate(${M.l},${M.t})`}>
            {yTicks.map((t) => (
              <g key={t} transform={`translate(0,${y(t)})`}>
                <line x2={innerW} className="grid" />
                <text x={-8} dy="0.32em" textAnchor="end" className="axis-text">{t}s</text>
              </g>
            ))}
            {bands.map((b, i) => (
              <g key={i}>
                <rect x={x(b.x0)} y={-4} width={Math.max(2, x(b.x1) - x(b.x0))} height={innerH + 8}
                  fill={b.kind === "SC" ? "var(--band-sc)" : b.kind === "VSC" ? "var(--band-vsc)" : "var(--band-red)"} />
                {x(b.x1) - x(b.x0) > 22 && <text x={x(b.x0) + 3} y={-8} className="axis-text">{b.kind}</text>}
              </g>
            ))}
            {selected.map(({ code, slot, pts }) => {
              const d = path(pts);
              return d ? <path key={code} d={d} fill="none" stroke={DRIVER_COLORS[slot]} strokeWidth={2.5} strokeLinejoin="round" /> : null;
            })}
            {selected.map(({ code, slot, pts }) => {
              const last = pts[pts.length - 1];
              return last ? <text key={code} x={x(last.lap - 0.5) + 6} y={y(last.value)} dy="0.32em" className="end-label end-label-sel">{code}</text> : null;
            })}
            {xTicks.map((t) => <text key={t} x={x(t - 0.5)} y={innerH + 18} textAnchor="middle" className="axis-text">{t}</text>)}
            {hover && <line x1={x(hover.lap - 0.5)} x2={x(hover.lap - 0.5)} y1={0} y2={innerH} className="crosshair" />}
            {hover && selected.map(({ code, slot }) => {
              const p = at(code, hover.lap);
              return p ? <circle key={code} cx={x(p.lap - 0.5)} cy={y(p.value)} r={5} fill={DRIVER_COLORS[slot]} stroke="var(--surface)" strokeWidth={2} /> : null;
            })}
          </g>
        </svg>
      )}
      {hover && (
        <Tip x={hover.x} y={hover.y} width={width}>
          <strong>Lap {hover.lap}</strong>
          {selected.length === 0 && <div className="tip-row">Select drivers above to read their gaps.</div>}
          {selected.map(({ code, slot }) => {
            const p = at(code, hover.lap);
            return (
              <div key={code} className="tip-row">
                <span className="swatch" style={{ background: DRIVER_COLORS[slot] }} /> {code} <span className="num">{p ? `${p.value.toFixed(1)} s` : "no gap"}</span>
              </div>
            );
          })}
        </Tip>
      )}
      <p className="axis-caption">
        {metric === "leader" ? "Seconds behind the leader" : "Seconds behind the car ahead"}, measured where each lap ends, so one point per lap. A lapped car&apos;s gap can be longer than a lap.
      </p>
    </div>
  );
}
