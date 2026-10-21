"use client";

import { scaleLinear } from "d3-scale";
import { useMemo, useState } from "react";
import { fmtSeconds } from "@/lib/format";
import { useWidth } from "@/lib/hooks";
import type { Circuit } from "@/lib/types";
import { Tip } from "./Tip";

const ROW = 28;
const TOP = 6;
const BOTTOM = 26;
const RIGHT = 62;

interface Row {
  circuit: Circuit;
  median: number;
  lo: number;
  hi: number;
}

export function PitLossChart({ circuits }: { circuits: Circuit[] }) {
  const [ref, width] = useWidth();
  const [hover, setHover] = useState<{ row: Row; x: number; y: number } | null>(null);

  const rows: Row[] = useMemo(
    () =>
      circuits
        .flatMap((c) => {
          const p = c.pit_loss;
          return p && p.median_pit_loss_s != null && p.p25_pit_loss_s != null && p.p75_pit_loss_s != null
            ? [{ circuit: c, median: p.median_pit_loss_s, lo: p.p25_pit_loss_s, hi: p.p75_pit_loss_s }]
            : [];
        })
        .sort((a, b) => b.median - a.median),
    [circuits],
  );
  if (rows.length === 0) return <p className="muted">No circuits have enough pit stops to show.</p>;

  const labelW = width < 520 ? 118 : 210;
  const innerW = Math.max(0, width - labelW - RIGHT);
  const height = TOP + rows.length * ROW + BOTTOM;
  const lo = Math.floor(Math.min(...rows.map((r) => r.lo)) - 1);
  const hi = Math.ceil(Math.max(...rows.map((r) => r.hi)) + 1);
  const x = scaleLinear().domain([lo, hi]).range([0, innerW]);
  const ticks = x.ticks(6);

  return (
    <div ref={ref} className="chart" style={{ minHeight: height }}>
      {width > 0 && (
        <svg
          width={width}
          height={height}
          role="img"
          aria-label={`Median pit loss for ${rows.length} circuits, from ${rows[rows.length - 1].median.toFixed(1)} to ${rows[0].median.toFixed(1)} seconds.`}
          onMouseLeave={() => setHover(null)}
        >
          <g transform={`translate(${labelW},${TOP})`}>
            {ticks.map((t) => (
              <g key={t} transform={`translate(${x(t)},0)`}>
                <line y2={rows.length * ROW} className="grid" />
                <text y={rows.length * ROW + 16} textAnchor="middle" className="axis-text">{t}</text>
              </g>
            ))}
            {rows.map((r, i) => (
              <g
                key={r.circuit.circuit_id}
                transform={`translate(0,${i * ROW})`}
                onMouseMove={(e) => {
                  const b = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
                  setHover({ row: r, x: e.clientX - b.left, y: e.clientY - b.top });
                }}
              >
                <rect x={-labelW} y={0} width={width} height={ROW} fill="transparent" />
                <g opacity={r.circuit.pit_loss?.is_reliable ? 1 : 0.5}>
                <text x={-10} y={ROW / 2} textAnchor="end" dominantBaseline="central" className="row-label row-label-name">
                  {r.circuit.circuit_name.length > (width < 520 ? 17 : 32) ? r.circuit.circuit_name.slice(0, width < 520 ? 16 : 31) + "…" : r.circuit.circuit_name}
                </text>
                <rect x={x(r.lo)} y={ROW / 2 - 3} width={Math.max(2, x(r.hi) - x(r.lo))} height={6} rx={3} className="range-bar" />
                <circle cx={x(r.median)} cy={ROW / 2} r={5} className="median-dot" />
                <text x={x(r.hi) + 10} y={ROW / 2} dominantBaseline="central" className="value-label">{r.median.toFixed(1)} s{r.circuit.pit_loss?.is_reliable ? "" : " (few stops)"}</text>
                </g>
              </g>
            ))}
          </g>
        </svg>
      )}
      {hover && (
        <Tip x={hover.x} y={hover.y} width={width}>
          <strong>{hover.row.circuit.circuit_name}</strong>
          <br />
          Median {fmtSeconds(hover.row.median)}, middle half {fmtSeconds(hover.row.lo)} to {fmtSeconds(hover.row.hi)}
          <br />
          {hover.row.circuit.pit_loss?.stops} stops in {hover.row.circuit.pit_loss?.sessions} sessions over {hover.row.circuit.pit_loss?.seasons} seasons
          {hover.row.circuit.pit_loss?.is_reliable ? null : <><br />Too few stops for a reliable figure.</>}
        </Tip>
      )}
      <p className="axis-caption">Seconds lost to a green-flag pit stop. The dot is the median and the bar spans the middle half of stops.</p>
    </div>
  );
}
