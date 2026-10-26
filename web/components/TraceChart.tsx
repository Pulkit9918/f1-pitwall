"use client";

import { scaleLinear } from "d3-scale";
import { curveStepAfter, line } from "d3-shape";
import { useMemo } from "react";
import { TRACE_COLORS, TRACE_DASH } from "@/lib/colors";
import { useWidth } from "@/lib/hooks";
import { lapLabel, nearestIndex, spreadLabels, type DrawnLap } from "@/lib/traces";
import { Tip } from "./Tip";

const M = { l: 52, r: 56, t: 10, b: 6 };

export interface Series {
  lap: DrawnLap;
  values: number[];
}

export interface PanelSpec {
  id: string;
  title: string;
  unit: string;
  height: number;
  step?: boolean;
  domain?: [number, number]; // fixed y range; otherwise fitted to the data
  symmetric?: boolean;
  fmt: (v: number) => string;
  tickFmt?: (v: number) => string;
  ticks?: number;
  caption?: string;
  labels?: boolean; // name each line at its right-hand end
}

export interface Hover {
  index: number;
  panel: string;
  x: number;
  y: number;
}

export function TraceChart({
  spec, series, dist, hover, onHover, last,
}: {
  spec: PanelSpec;
  series: Series[];
  dist: number[];
  hover: Hover | null;
  onHover: (h: Hover | null) => void;
  last: boolean;
}) {
  const [ref, width] = useWidth();
  const { height } = spec;
  const innerW = Math.max(0, width - M.l - M.r);
  const innerH = height - M.t - M.b;
  const total = dist[dist.length - 1] || 1;
  const x = useMemo(() => scaleLinear().domain([0, total]).range([0, innerW]), [total, innerW]);
  const y = useMemo(() => {
    let [lo, hi] = spec.domain ?? [0, 1];
    if (!spec.domain) {
      const all = series.flatMap((s) => s.values);
      lo = Math.min(0, ...all);
      hi = Math.max(...all, 1);
      if (spec.symmetric) {
        const m = Math.max(Math.abs(lo), Math.abs(hi), 0.5);
        lo = -m;
        hi = m;
      }
    }
    const s = scaleLinear().domain([lo, hi]).range([innerH, 0]);
    return spec.domain ? s : s.nice();
  }, [spec, series, innerH]);
  const path = useMemo(() => {
    const l = line<number>().x((_, i) => x(dist[i])).y((v) => y(v));
    return spec.step ? l.curve(curveStepAfter) : l;
  }, [x, y, dist, spec.step]);
  const mine = hover && hover.panel === spec.id ? hover : null;
  const yTicks = y.ticks(spec.ticks ?? 4);
  const xTicks = x.ticks(Math.max(3, Math.floor(innerW / 90)));
  const ends = spec.labels ? spreadLabels(series.map((s) => y(s.values[s.values.length - 1])), 12, 0, innerH) : [];

  return (
    <div ref={ref} className="chart trace-panel" style={{ minHeight: height }}>
      <p className="trace-title">{spec.title} <span className="muted">{spec.unit}</span></p>
      {width > 0 && (
        <svg
          width={width} height={height + (last ? 22 : 0)} role="img" aria-label={`${spec.title} against distance, one line per lap.`}
          onMouseLeave={() => onHover(null)}
          onMouseMove={(e) => {
            const r = e.currentTarget.getBoundingClientRect();
            const d = x.invert(e.clientX - r.left - M.l);
            if (d < -total * 0.02 || d > total * 1.02) return onHover(null);
            onHover({ index: nearestIndex(dist, d), panel: spec.id, x: e.clientX - r.left, y: e.clientY - r.top });
          }}
        >
          <g transform={`translate(${M.l},${M.t})`}>
            {yTicks.map((t) => (
              <g key={t} transform={`translate(0,${y(t)})`}>
                <line x2={innerW} className={t === 0 && spec.symmetric ? "trace-zero" : "grid"} />
                <text x={-8} dy="0.32em" textAnchor="end" className="axis-text">{(spec.tickFmt ?? spec.fmt)(t)}</text>
              </g>
            ))}
            {xTicks.map((t) => <line key={t} x1={x(t)} x2={x(t)} y1={0} y2={innerH} className="grid-v" />)}
            {series.map(({ lap, values }) => (
              <path
                key={`${lap.pick.driver}:${lap.pick.lap}`} d={path(values) ?? undefined} fill="none"
                stroke={TRACE_COLORS[lap.slot]} strokeWidth={lap.slot === 0 ? 2.25 : 1.75} strokeLinejoin="round"
                strokeDasharray={TRACE_DASH[lap.slot]}
              />
            ))}
            {spec.labels && series.map(({ lap, values }, i) => (
              <text key={`l${lap.pick.driver}:${lap.pick.lap}`} x={innerW + 6} y={ends[i]} dy="0.32em" className="end-label end-label-sel">
                {lap.pick.driver}{" "}<tspan className="muted">{lap.pick.lap}</tspan>
                <title>{lapLabel(lap.pick)} ends {spec.fmt(values[values.length - 1])}</title>
              </text>
            ))}
            {last && xTicks.map((t) => <text key={t} x={x(t)} y={innerH + 18} textAnchor="middle" className="axis-text">{t === 0 ? "start" : t >= total ? "" : `${t} m`}</text>)}
            {hover && <line x1={x(dist[hover.index])} x2={x(dist[hover.index])} y1={0} y2={innerH} className="crosshair" />}
            {hover && series.map(({ lap, values }) => (
              <circle key={`c${lap.pick.driver}:${lap.pick.lap}`} cx={x(dist[hover.index])} cy={y(values[hover.index])} r={3.5}
                fill={TRACE_COLORS[lap.slot]} stroke="var(--surface)" strokeWidth={1.5} />
            ))}
          </g>
        </svg>
      )}
      {mine && (
        <Tip x={mine.x} y={mine.y} width={width}>
          <strong>{Math.round(dist[mine.index])} m</strong>
          {series.map(({ lap, values }) => (
            <div key={`t${lap.pick.driver}:${lap.pick.lap}`} className="tip-row">
              <span className="swatch" style={{ background: TRACE_COLORS[lap.slot] }} /> {lapLabel(lap.pick)}
              <span className="num">{spec.fmt(values[mine.index])}</span>
            </div>
          ))}
        </Tip>
      )}
      {spec.caption && <p className="axis-caption">{spec.caption}</p>}
    </div>
  );
}
