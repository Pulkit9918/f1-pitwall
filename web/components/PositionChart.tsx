"use client";

import { scaleLinear } from "d3-scale";
import { line } from "d3-shape";
import { useId, useMemo, useState } from "react";
import { DRIVER_COLORS } from "@/lib/colors";
import { useWidth } from "@/lib/hooks";
import { driverOrder, maxLap, periodBands, positionSeries } from "@/lib/race";
import type { Point, SessionDoc } from "@/lib/types";
import { Tip } from "./Tip";

const M = { l: 34, r: 40, t: 22, b: 28 };

export function PositionChart({ doc, slots }: { doc: SessionDoc; slots: (string | null)[] }) {
  const [ref, width] = useWidth();
  const uid = useId().replace(/:/g, "");
  const [hover, setHover] = useState<{ lap: number; x: number; y: number } | null>(null);

  const laps = maxLap(doc);
  const order = useMemo(() => driverOrder(doc), [doc]);
  const bands = useMemo(() => periodBands(doc), [doc]);
  const all = useMemo(() => order.map((code) => ({ code, pts: positionSeries(doc, code) })), [doc, order]);
  const maxPos = Math.max(2, ...all.flatMap((s) => s.pts.map((p) => p.value)));
  const height = Math.max(300, M.t + M.b + maxPos * 15);

  const innerW = Math.max(0, width - M.l - M.r);
  const innerH = height - M.t - M.b;
  const x = scaleLinear().domain([0, Math.max(laps, 1)]).range([0, innerW]);
  const y = scaleLinear().domain([1, maxPos]).range([0, innerH]);
  const path = line<Point>().x((p) => x(p.lap - 0.5)).y((p) => y(p.value));
  const yTicks = [1, ...[5, 10, 15, 20].filter((t) => t < maxPos), maxPos].filter((t, i, a) => a.indexOf(t) === i);
  const tickStep = laps > 60 ? 10 : 5;
  const xTicks = Array.from({ length: Math.floor(laps / tickStep) }, (_, i) => (i + 1) * tickStep);
  const selected = slots.flatMap((code, slot) => (code ? [{ code, slot }] : []));
  const slotOf = (code: string) => slots.indexOf(code);

  return (
    <div ref={ref} className="chart" style={{ minHeight: height }}>
      {width > 0 && (
        <svg
          width={width}
          height={height}
          role="img"
          aria-label={`Running order by lap for ${all.length} drivers.`}
          onMouseLeave={() => setHover(null)}
          onMouseMove={(e) => {
            const r = e.currentTarget.getBoundingClientRect();
            const lap = Math.min(laps, Math.max(1, Math.round(x.invert(e.clientX - r.left - M.l) + 0.5)));
            setHover({ lap, x: e.clientX - r.left, y: e.clientY - r.top });
          }}
        >
          <defs>
            <pattern id={`${uid}-hatch`} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <rect width="6" height="6" fill="var(--band-vsc)" />
              <line x1="0" y1="0" x2="0" y2="6" stroke="var(--band-vsc-line)" strokeWidth="2" />
            </pattern>
          </defs>
          <g transform={`translate(${M.l},${M.t})`}>
            {yTicks.map((t) => (
              <g key={t} transform={`translate(0,${y(t)})`}>
                <line x2={innerW} className="grid" />
                <text x={-8} dy="0.32em" textAnchor="end" className="axis-text">P{t}</text>
              </g>
            ))}
            {bands.map((b, i) => (
              <g key={i}>
                <rect
                  x={x(b.x0)} y={-4} width={Math.max(2, x(b.x1) - x(b.x0))} height={innerH + 8}
                  fill={b.kind === "SC" ? "var(--band-sc)" : b.kind === "VSC" ? `url(#${uid}-hatch)` : "var(--band-red)"}
                />
                {x(b.x1) - x(b.x0) > 22 && <text x={x(b.x0) + 3} y={-8} className="axis-text">{b.kind}</text>}
              </g>
            ))}
            {all.filter((s) => slotOf(s.code) < 0).map((s) => {
              const d = path(s.pts);
              return d ? <path key={s.code} d={d} fill="none" className="line-muted" strokeWidth={1} /> : null;
            })}
            {selected.map(({ code, slot }) => {
              const pts = all.find((s) => s.code === code)?.pts ?? [];
              const d = path(pts);
              return d ? <path key={code} d={d} fill="none" stroke={DRIVER_COLORS[slot]} strokeWidth={2.5} strokeLinejoin="round" /> : null;
            })}
            {all.map((s) => {
              const last = s.pts[s.pts.length - 1];
              if (!last) return null;
              const sel = slotOf(s.code) >= 0;
              return (
                <text key={s.code} x={x(last.lap - 0.5) + 6} y={y(last.value)} dy="0.32em" className={sel ? "end-label end-label-sel" : "end-label"}>
                  {s.code}
                </text>
              );
            })}
            {xTicks.map((t) => (
              <text key={t} x={x(t - 0.5)} y={innerH + 18} textAnchor="middle" className="axis-text">{t}</text>
            ))}
            {hover && <line x1={x(hover.lap - 0.5)} x2={x(hover.lap - 0.5)} y1={0} y2={innerH} className="crosshair" />}
            {hover &&
              selected.map(({ code, slot }) => {
                const p = all.find((s) => s.code === code)?.pts.find((q) => q.lap === hover.lap);
                return p ? <circle key={code} cx={x(p.lap - 0.5)} cy={y(p.value)} r={5} fill={DRIVER_COLORS[slot]} stroke="var(--surface)" strokeWidth={2} /> : null;
              })}
          </g>
        </svg>
      )}
      {hover && (
        <Tip x={hover.x} y={hover.y} width={width}>
          <strong>Lap {hover.lap}</strong>
          {selected.length === 0 && <div className="tip-row">Select drivers above to read their positions.</div>}
          {selected.map(({ code, slot }) => {
            const p = all.find((s) => s.code === code)?.pts.find((q) => q.lap === hover.lap);
            return (
              <div key={code} className="tip-row">
                <span className="swatch" style={{ background: DRIVER_COLORS[slot] }} /> {code} <span className="num">{p ? `P${p.value}` : "no position"}</span>
              </div>
            );
          })}
        </Tip>
      )}
      <p className="axis-caption">Running order at the end of each lap. Lap number along the bottom.</p>
    </div>
  );
}
