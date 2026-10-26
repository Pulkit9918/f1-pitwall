"use client";

import { scaleLinear } from "d3-scale";
import { line } from "d3-shape";
import { useState } from "react";
import { useWidth } from "@/lib/hooks";
import type { Pair } from "@/lib/laps";
import { Tip } from "./Tip";

const M = { l: 48, r: 16, t: 22, b: 28 };

export function LapDeltaChart({ pairs, a, b }: { pairs: Pair[]; a: string; b: string }) {
  const [ref, width] = useWidth();
  const [hover, setHover] = useState<{ i: number; x: number; y: number } | null>(null);
  const height = 260;
  if (pairs.length === 0) return <p className="muted">No lap was driven cleanly by both drivers.</p>;
  const innerW = Math.max(0, width - M.l - M.r);
  const innerH = height - M.t - M.b;
  const top = Math.max(0.5, ...pairs.map((p) => Math.abs(p.lap)));
  const x = scaleLinear().domain([Math.min(...pairs.map((p) => p.n)), Math.max(...pairs.map((p) => p.n), 1)]).range([0, innerW]);
  const y = scaleLinear().domain([-top, top]).nice().range([innerH, 0]);
  const path = line<Pair>().x((p) => x(p.n)).y((p) => y(p.lap))(pairs);
  const sign = (v: number) => `${v > 0 ? "+" : v < 0 ? "-" : ""}${Math.abs(v).toFixed(3)} s`;
  const h = hover ? pairs[hover.i] : null;
  return (
    <div ref={ref} className="chart" style={{ minHeight: height }}>
      {width > 0 && (
        <svg width={width} height={height} role="img" aria-label={`Lap time of ${a} minus ${b} on each lap both drove cleanly.`}
          onMouseLeave={() => setHover(null)}
          onMouseMove={(e) => {
            const r = e.currentTarget.getBoundingClientRect();
            const n = x.invert(e.clientX - r.left - M.l);
            let best = 0;
            pairs.forEach((p, i) => { if (Math.abs(p.n - n) < Math.abs(pairs[best].n - n)) best = i; });
            setHover({ i: best, x: e.clientX - r.left, y: e.clientY - r.top });
          }}>
          <g transform={`translate(${M.l},${M.t})`}>
            {y.ticks(5).map((t) => (
              <g key={t} transform={`translate(0,${y(t)})`}>
                <line x2={innerW} className={t === 0 ? "trace-zero" : "grid"} />
                <text x={-8} dy="0.32em" textAnchor="end" className="axis-text">{t > 0 ? "+" : ""}{t}</text>
              </g>
            ))}
            <text x={innerW} y={-8} textAnchor="end" className="axis-text">{a} slower</text>
            <text x={innerW} y={innerH - 6} textAnchor="end" className="axis-text">{b} slower</text>
            {path && <path d={path} fill="none" stroke="var(--ink-2)" strokeWidth={1.5} strokeLinejoin="round" />}
            {pairs.map((p) => <circle key={p.n} cx={x(p.n)} cy={y(p.lap)} r={2.5} fill={p.lap > 0 ? "var(--ink)" : "var(--ground)"} stroke="var(--ink)" strokeWidth={1.5} />)}
            {x.ticks(Math.max(3, Math.floor(innerW / 80))).map((t) => <text key={t} x={x(t)} y={innerH + 18} textAnchor="middle" className="axis-text">{t}</text>)}
            {hover && h && <line x1={x(h.n)} x2={x(h.n)} y1={0} y2={innerH} className="crosshair" />}
          </g>
        </svg>
      )}
      {hover && h && (
        <Tip x={hover.x} y={hover.y} width={width}>
          <strong>Lap {h.n}</strong>
          <div className="tip-row">Lap <span className="num">{sign(h.lap)}</span></div>
          {h.sectors.map((s, k) => <div key={k} className="tip-row">Sector {k + 1} <span className="num">{sign(s)}</span></div>)}
          <div className="tip-row muted">{h.lap > 0 ? `${a} was slower` : h.lap < 0 ? `${b} was slower` : "level"}</div>
        </Tip>
      )}
      <p className="axis-caption">
        Lap time of {a} minus {b}, on each lap both drove cleanly (a clean lap as the lap table defines it, and no pit lane or deleted time).
        Filled dots are laps {a} lost, hollow dots laps {a} won.
      </p>
    </div>
  );
}
