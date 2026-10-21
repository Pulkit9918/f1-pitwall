"use client";

import { scaleLinear } from "d3-scale";
import { line } from "d3-shape";
import { useState } from "react";
import { DRIVER_COLORS } from "@/lib/colors";
import { useWidth } from "@/lib/hooks";
import { seriesPoints, type DriverSeries, type RoundPoint } from "@/lib/seasons";
import { Tip } from "./Tip";

const M = { l: 40, r: 40, t: 14, b: 28 };

export type Metric = "points" | "position";

export function ProgressionChart({ rounds, series, slots, metric }: { rounds: number[]; series: DriverSeries[]; slots: (string | null)[]; metric: Metric }) {
  const [ref, width] = useWidth();
  const [hover, setHover] = useState<{ round: number; x: number; y: number } | null>(null);
  const height = 340;
  const values = (s: DriverSeries) => seriesPoints(rounds, metric === "points" ? s.cum : s.pos);
  const all = series.map((s) => ({ s, pts: values(s) }));
  const maxV = Math.max(1, ...all.flatMap((a) => a.pts.map((p) => p.value)));
  const innerW = Math.max(0, width - M.l - M.r);
  const innerH = height - M.t - M.b;
  const x = scaleLinear().domain([Math.min(...rounds), Math.max(...rounds, 1)]).range([0, innerW]);
  const y = metric === "points" ? scaleLinear().domain([0, maxV]).nice().range([innerH, 0]) : scaleLinear().domain([1, Math.max(2, maxV)]).range([0, innerH]);
  const path = line<RoundPoint>().x((p) => x(p.round)).y((p) => y(p.value));
  const yTicks = metric === "points" ? y.ticks(5) : [1, 5, 10, 15, 20].filter((t) => t <= Math.max(2, maxV));
  const selected = slots.flatMap((id, slot) => (id ? [{ id, slot }] : []));
  const slotOf = (id: string) => slots.indexOf(id);
  const fmt = (v: number) => (metric === "points" ? `${v}` : `P${v}`);
  const at = (id: string, round: number) => all.find((a) => a.s.driver_id === id)?.pts.find((p) => p.round === round);

  return (
    <div ref={ref} className="chart" style={{ minHeight: height }}>
      {width > 0 && rounds.length > 0 && (
        <svg
          width={width} height={height} role="img"
          aria-label={`${metric === "points" ? "Cumulative points" : "Championship position"} after each round for ${series.length} drivers.`}
          onMouseLeave={() => setHover(null)}
          onMouseMove={(e) => {
            const r = e.currentTarget.getBoundingClientRect();
            const raw = x.invert(e.clientX - r.left - M.l);
            const round = rounds.reduce((b, v) => (Math.abs(v - raw) < Math.abs(b - raw) ? v : b), rounds[0]);
            setHover({ round, x: e.clientX - r.left, y: e.clientY - r.top });
          }}
        >
          <g transform={`translate(${M.l},${M.t})`}>
            {yTicks.map((t) => (
              <g key={t} transform={`translate(0,${y(t)})`}>
                <line x2={innerW} className="grid" />
                <text x={-8} dy="0.32em" textAnchor="end" className="axis-text">{fmt(t)}</text>
              </g>
            ))}
            {all.filter((a) => slotOf(a.s.driver_id) < 0).map((a) => {
              const d = path(a.pts);
              return d ? <path key={a.s.driver_id} d={d} fill="none" className="line-muted" strokeWidth={1} /> : null;
            })}
            {selected.map(({ id, slot }) => {
              const d = path(all.find((a) => a.s.driver_id === id)?.pts ?? []);
              return d ? <path key={id} d={d} fill="none" stroke={DRIVER_COLORS[slot]} strokeWidth={2.5} strokeLinejoin="round" /> : null;
            })}
            {all.map((a) => {
              const last = a.pts[a.pts.length - 1];
              if (!last) return null;
              const sel = slotOf(a.s.driver_id) >= 0;
              return <text key={a.s.driver_id} x={x(last.round) + 6} y={y(last.value)} dy="0.32em" className={sel ? "end-label end-label-sel" : "end-label"}>{a.s.code}</text>;
            })}
            {rounds.filter((r, i) => rounds.length <= 12 || i % 2 === 0).map((r) => (
              <text key={r} x={x(r)} y={innerH + 18} textAnchor="middle" className="axis-text">{r}</text>
            ))}
            {hover && <line x1={x(hover.round)} x2={x(hover.round)} y1={0} y2={innerH} className="crosshair" />}
            {hover && selected.map(({ id, slot }) => {
              const p = at(id, hover.round);
              return p ? <circle key={id} cx={x(p.round)} cy={y(p.value)} r={5} fill={DRIVER_COLORS[slot]} stroke="var(--surface)" strokeWidth={2} /> : null;
            })}
          </g>
        </svg>
      )}
      {hover && (
        <Tip x={hover.x} y={hover.y} width={width}>
          <strong>After round {hover.round}</strong>
          {selected.length === 0 && <div className="tip-row">Select drivers above to read their {metric === "points" ? "points" : "positions"}.</div>}
          {selected.map(({ id, slot }) => {
            const p = at(id, hover.round);
            const code = series.find((s) => s.driver_id === id)?.code ?? id;
            return (
              <div key={id} className="tip-row">
                <span className="swatch" style={{ background: DRIVER_COLORS[slot] }} /> {code} <span className="num">{p ? fmt(p.value) : "no entry"}</span>
              </div>
            );
          })}
        </Tip>
      )}
      <p className="axis-caption">
        {metric === "points" ? "Cumulative points" : "Championship position"} after each round, race and sprint points together. Round number along the bottom.
      </p>
    </div>
  );
}
