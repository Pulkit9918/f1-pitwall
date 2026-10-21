"use client";

import { scaleLinear } from "d3-scale";
import { line } from "d3-shape";
import { useId, useMemo, useState } from "react";
import { DRIVER_COLORS } from "@/lib/colors";
import { fmtLap, fmtLapTick } from "@/lib/format";
import { useWidth } from "@/lib/hooks";
import { cleanSeries, lapDomain, maxLap, periodBands } from "@/lib/race";
import type { Point, SessionDoc } from "@/lib/types";
import { Tip } from "./Tip";

const M = { l: 58, r: 52, t: 22, b: 28 };
const HEIGHT = 320;

interface Series {
  code: string;
  slot: number;
  pts: Point[];
}

// Break the line wherever a lap is missing (pit laps, safety car laps and other laps that are not clean).
function withGaps(pts: Point[]): Point[] {
  const out: Point[] = [];
  pts.forEach((p, i) => {
    if (i > 0 && p.lap - pts[i - 1].lap > 1) out.push({ lap: p.lap - 1, value: NaN });
    out.push(p);
  });
  return out;
}

export function LapChart({ doc, slots }: { doc: SessionDoc; slots: (string | null)[] }) {
  const [ref, width] = useWidth();
  const uid = useId().replace(/:/g, "");
  const [hoverLap, setHoverLap] = useState<{ lap: number; x: number; y: number } | null>(null);

  const laps = maxLap(doc);
  const bands = useMemo(() => periodBands(doc), [doc]);
  const series: Series[] = useMemo(
    () => slots.flatMap((code, slot) => (code ? [{ code, slot, pts: cleanSeries(doc, code) }] : [])),
    [doc, slots],
  );
  const domain = useMemo(() => lapDomain(series.map((s) => s.pts)), [series]);

  if (series.length === 0) return <p className="muted">Pick up to three drivers to compare their lap times.</p>;
  if (!domain) return <p className="muted">These drivers have no clean laps in this session.</p>;

  const innerW = Math.max(0, width - M.l - M.r);
  const innerH = HEIGHT - M.t - M.b;
  const x = scaleLinear().domain([0, Math.max(laps, 1)]).range([0, innerW]);
  const y = scaleLinear().domain(domain).range([innerH, 0]);
  const path = line<Point>()
    .defined((p) => Number.isFinite(p.value))
    .x((p) => x(p.lap - 0.5))
    .y((p) => y(p.value));
  const yTicks = y.ticks(5);
  const tickStep = laps > 60 ? 10 : 5;
  const xTicks = Array.from({ length: Math.floor(laps / tickStep) }, (_, i) => (i + 1) * tickStep);

  return (
    <div ref={ref} className="chart" style={{ minHeight: HEIGHT }}>
      {width > 0 && (
        <svg
          width={width}
          height={HEIGHT}
          role="img"
          aria-label={`Clean lap times for ${series.map((s) => s.code).join(", ")} over ${laps} laps.`}
          onMouseLeave={() => setHoverLap(null)}
          onMouseMove={(e) => {
            const r = e.currentTarget.getBoundingClientRect();
            const px = e.clientX - r.left - M.l;
            const lap = Math.min(laps, Math.max(1, Math.round(x.invert(px) + 0.5)));
            setHoverLap({ lap, x: e.clientX - r.left, y: e.clientY - r.top });
          }}
        >
          <defs>
            <clipPath id={`${uid}-clip`}><rect x={0} y={-4} width={innerW} height={innerH + 8} /></clipPath>
            <pattern id={`${uid}-hatch`} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
              <rect width="6" height="6" fill="var(--band-vsc)" />
              <line x1="0" y1="0" x2="0" y2="6" stroke="var(--band-vsc-line)" strokeWidth="2" />
            </pattern>
          </defs>
          <g transform={`translate(${M.l},${M.t})`}>
            {yTicks.map((t) => (
              <g key={t} transform={`translate(0,${y(t)})`}>
                <line x2={innerW} className="grid" />
                <text x={-8} dy="0.32em" textAnchor="end" className="axis-text">{fmtLapTick(t)}</text>
              </g>
            ))}
            {bands.map((b, i) => (
              <g key={i}>
                <rect
                  x={x(b.x0)} y={0} width={Math.max(2, x(b.x1) - x(b.x0))} height={innerH}
                  fill={b.kind === "SC" ? "var(--band-sc)" : b.kind === "VSC" ? `url(#${uid}-hatch)` : "var(--band-red)"}
                />
                {x(b.x1) - x(b.x0) > 22 && <text x={x(b.x0) + 3} y={-8} className="axis-text">{b.kind}</text>}
              </g>
            ))}
            <g clipPath={`url(#${uid}-clip)`}>
              {series.map((s) => {
                const d = path(withGaps(s.pts));
                return d ? <path key={s.code} d={d} fill="none" stroke={DRIVER_COLORS[s.slot]} strokeWidth={2} strokeLinejoin="round" /> : null;
              })}
              {series.map((s) =>
                s.pts.map((p) => (
                  <circle key={`${s.code}-${p.lap}`} cx={x(p.lap - 0.5)} cy={y(p.value)} r={2} fill={DRIVER_COLORS[s.slot]} />
                )),
              )}
            </g>
            {xTicks.map((t) => (
              <text key={t} x={x(t - 0.5)} y={innerH + 18} textAnchor="middle" className="axis-text">{t}</text>
            ))}
            {hoverLap && (
              <g>
                <line x1={x(hoverLap.lap - 0.5)} x2={x(hoverLap.lap - 0.5)} y1={0} y2={innerH} className="crosshair" />
                {series.map((s) => {
                  const p = s.pts.find((q) => q.lap === hoverLap.lap);
                  return p ? (
                    <circle key={s.code} cx={x(p.lap - 0.5)} cy={y(p.value)} r={5} fill={DRIVER_COLORS[s.slot]} stroke="var(--surface)" strokeWidth={2} />
                  ) : null;
                })}
              </g>
            )}
          </g>
        </svg>
      )}
      {hoverLap && (
        <Tip x={hoverLap.x} y={hoverLap.y} width={width}>
          <strong>Lap {hoverLap.lap}</strong>
          {series.map((s) => {
            const p = s.pts.find((q) => q.lap === hoverLap.lap);
            return (
              <div key={s.code} className="tip-row">
                <span className="swatch" style={{ background: DRIVER_COLORS[s.slot] }} /> {s.code}{" "}
                <span className="num">{p ? fmtLap(p.value) : "no clean lap"}</span>
              </div>
            );
          })}
        </Tip>
      )}
      <p className="axis-caption">Clean laps only, so pit laps, safety car laps and traffic are left out. Lap number along the bottom.</p>
    </div>
  );
}
