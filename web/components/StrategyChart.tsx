"use client";

import { scaleLinear } from "d3-scale";
import { useId, useMemo, useState } from "react";
import { compoundColor, compoundLetter, onCompound } from "@/lib/colors";
import { fmtDeg, fmtLap } from "@/lib/format";
import { useWidth } from "@/lib/hooks";
import { driverOrder, maxLap, periodBands, stintRows } from "@/lib/race";
import type { SessionDoc, Stint } from "@/lib/types";
import { Tip } from "./Tip";

const LABEL_W = 46;
const TOP = 22;
const BOTTOM = 24;

export function StrategyChart({ doc, compact = false }: { doc: SessionDoc; compact?: boolean }) {
  const [ref, width] = useWidth();
  const uid = useId().replace(/:/g, "");
  const [hover, setHover] = useState<{ stint: Stint; x: number; y: number } | null>(null);
  const [asTable, setAsTable] = useState(false);

  const order = useMemo(() => driverOrder(doc), [doc]);
  const stints = useMemo(() => stintRows(doc), [doc]);
  const bands = useMemo(() => periodBands(doc), [doc]);
  const laps = maxLap(doc);
  const rowH = compact ? 17 : 24;
  const pad = compact ? 3 : 4;
  const height = TOP + order.length * rowH + BOTTOM;
  const innerW = Math.max(0, width - LABEL_W - 8);
  const x = scaleLinear().domain([0, Math.max(laps, 1)]).range([0, innerW]);
  const rank = (c: string) => {
    const i = ["SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"].indexOf(c);
    return i < 0 ? 9 : i;
  };
  const compounds = [...new Set(stints.map((s) => s.compound))].sort((a, b) => rank(a) - rank(b));
  const tickStep = laps > 60 ? 10 : 5;
  const ticks = Array.from({ length: Math.floor(laps / tickStep) }, (_, i) => (i + 1) * tickStep);

  if (stints.length === 0) return <p className="muted">No tyre stints were recorded for this session.</p>;

  return (
    <div>
      <div className="chart-head">
        <ul className="legend" aria-label="Tyre compounds">
          {compounds.map((c) => (
            <li key={c}>
              <span className="swatch" style={{ background: compoundColor(c) }} /> {c.charAt(0) + c.slice(1).toLowerCase()}
            </li>
          ))}
          {bands.length > 0 && (
            <>
              <li><span className="swatch band-sc" /> Safety car</li>
              <li><span className="swatch band-vsc" /> Virtual safety car</li>
              <li><span className="swatch band-red" /> Red flag</li>
            </>
          )}
        </ul>
        <button type="button" className="link-button" onClick={() => setAsTable((v) => !v)} aria-pressed={asTable}>
          {asTable ? "Show chart" : "Show as table"}
        </button>
      </div>

      {asTable ? (
        <StintTable stints={stints} order={order} />
      ) : (
        <div ref={ref} className="chart" style={{ minHeight: height }}>
          {width > 0 && (
            <svg
              width={width}
              height={height}
              role="img"
              aria-label={`Tyre strategy for ${order.length} drivers over ${laps} laps. A table version is available.`}
              onMouseLeave={() => setHover(null)}
            >
              <defs>
                <pattern id={`${uid}-hatch`} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                  <rect width="6" height="6" fill="var(--band-vsc)" />
                  <line x1="0" y1="0" x2="0" y2="6" stroke="var(--band-vsc-line)" strokeWidth="2" />
                </pattern>
              </defs>
              <g transform={`translate(${LABEL_W},${TOP})`}>
                {bands.map((b, i) => (
                  <g key={i}>
                    <rect
                      x={x(b.x0)}
                      y={-6}
                      width={Math.max(2, x(b.x1) - x(b.x0))}
                      height={order.length * rowH + 6}
                      fill={b.kind === "SC" ? "var(--band-sc)" : b.kind === "VSC" ? `url(#${uid}-hatch)` : "var(--band-red)"}
                    />
                    {x(b.x1) - x(b.x0) > 22 && (
                      <text x={x(b.x0) + 3} y={-10} className="axis-text">{b.kind}</text>
                    )}
                  </g>
                ))}
                {order.map((d, row) => (
                  <g key={d} transform={`translate(0,${row * rowH})`}>
                    <text x={-8} y={rowH / 2} textAnchor="end" dominantBaseline="central" className="row-label">{d}</text>
                    {stints.filter((s) => s.driver === d).map((s) => {
                      const x0 = x(s.startLap - 1) + 1;
                      const w = Math.max(2, x(s.endLap) - x(s.startLap - 1) - 2);
                      return (
                        <g
                          key={s.stint}
                          onMouseMove={(e) => {
                            const r = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
                            setHover({ stint: s, x: e.clientX - r.left, y: e.clientY - r.top });
                          }}
                        >
                          <rect x={x0} y={pad} width={w} height={rowH - pad * 2} rx={2} fill={compoundColor(s.compound)} />
                          {w > 16 && (
                            <text x={x0 + w / 2} y={rowH / 2} textAnchor="middle" dominantBaseline="central" className="bar-letter" fill={onCompound(s.compound)}>
                              {compoundLetter(s.compound)}
                            </text>
                          )}
                        </g>
                      );
                    })}
                  </g>
                ))}
                <g transform={`translate(0,${order.length * rowH + 4})`}>
                  {ticks.map((t) => (
                    <text key={t} x={x(t)} y={14} textAnchor="middle" className="axis-text">{t}</text>
                  ))}
                </g>
              </g>
            </svg>
          )}
          {hover && (
            <Tip x={hover.x} y={hover.y} width={width}>
              <strong>{hover.stint.driver}</strong> stint {hover.stint.stint}, {hover.stint.compound.toLowerCase()}
              <br />
              Laps {hover.stint.startLap} to {hover.stint.endLap} ({hover.stint.laps})
              <br />
              Median clean lap {fmtLap(hover.stint.medianCleanLap)}
              <br />
              Tyre wear {fmtDeg(hover.stint.degradation)}
            </Tip>
          )}
        </div>
      )}
      {!asTable && <p className="axis-caption">Lap number. Letters mark the compound: S soft, M medium, H hard, I intermediate, W wet.</p>}
    </div>
  );
}

function StintTable({ stints, order }: { stints: Stint[]; order: string[] }) {
  const rows = [...stints].sort((a, b) => order.indexOf(a.driver) - order.indexOf(b.driver) || a.stint - b.stint);
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr><th>Driver</th><th>Stint</th><th>Tyre</th><th className="num">Laps</th><th className="num">Median clean lap</th><th className="num">Tyre wear</th></tr>
        </thead>
        <tbody>
          {rows.map((s) => (
            <tr key={`${s.driver}-${s.stint}`}>
              <td>{s.driver}</td>
              <td>{s.stint}</td>
              <td>{s.compound.charAt(0) + s.compound.slice(1).toLowerCase()}</td>
              <td className="num">{s.startLap} to {s.endLap}</td>
              <td className="num">{fmtLap(s.medianCleanLap)}</td>
              <td className="num">{fmtDeg(s.degradation)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
