"use client";

import { useState } from "react";
import { TRACE_COLORS } from "@/lib/colors";
import { fmtLap } from "@/lib/format";
import { MAX_LAPS, fastestLap, lapLabel, lapOption, pickKey, type Pick, type TraceSession } from "@/lib/traces";
import { CompoundChip } from "./CompoundChip";

export function LapPicker({
  session, order, picks, slots, refKey, onAdd, onRemove, onReference,
}: {
  session: TraceSession;
  order: string[];
  picks: Pick[];
  slots: Record<string, number>;
  refKey: string;
  onAdd: (p: Pick) => void;
  onRemove: (p: Pick) => void;
  onReference: (p: Pick) => void;
}) {
  const [driver, setDriver] = useState(order[0] ?? "");
  const [lap, setLap] = useState<number | null>(null);
  const laps = session.drivers.find((d) => d.code === driver)?.laps ?? [];
  const chosen = lap !== null ? laps.find((l) => l.n === lap) : undefined;
  const best = fastestLap(laps);
  const full = picks.length >= MAX_LAPS;
  const canAdd = !!chosen && chosen.k !== undefined && !full && !picks.some((p) => pickKey(p) === `${driver}:${chosen.n}`);

  return (
    <div className="lap-picker">
      <ul className="lap-chips" aria-label="Laps being compared">
        {picks.map((p) => {
          const meta = session.drivers.find((d) => d.code === p.driver)?.laps.find((l) => l.n === p.lap);
          const isRef = pickKey(p) === refKey;
          return (
            <li key={pickKey(p)} className={`lap-chip${isRef ? " lap-chip-ref" : ""}`}>
              <span className="swatch" style={{ background: TRACE_COLORS[slots[pickKey(p)] ?? 0] }} />
              <span className="lap-chip-name">{lapLabel(p)}</span>
              <CompoundChip compound={meta?.c} />
              <span className="num muted">{fmtLap(meta?.t)}</span>
              {meta?.k === 0 && <span className="muted small" title="The speed channel did not agree with the positions on this lap, so it adds to the time delta only.">time only</span>}
              <button type="button" className="link-button small" disabled={isRef} onClick={() => onReference(p)} aria-pressed={isRef}
                title="Time deltas are measured against this lap">{isRef ? "reference" : "use as reference"}</button>
              <button type="button" className="lap-remove" onClick={() => onRemove(p)} aria-label={`Remove ${lapLabel(p)}`}>×</button>
            </li>
          );
        })}
        {picks.length === 0 && <li className="muted">No laps chosen. Add one below.</li>}
      </ul>

      <div className="lap-add">
        <label className="field">
          <span>Driver</span>
          <select value={driver} onChange={(e) => { setDriver(e.target.value); setLap(null); }}>
            {session.drivers.map((d) => <option key={d.code} value={d.code}>{d.code}{d.team ? `, ${d.team}` : ""}</option>)}
          </select>
        </label>
        <label className="field lap-select">
          <span>Lap</span>
          <select value={lap ?? ""} onChange={(e) => setLap(e.target.value ? Number(e.target.value) : null)}>
            <option value="">Choose a lap</option>
            {laps.map((l) => <option key={l.n} value={l.n} disabled={l.k === undefined}>{lapOption(l, fmtLap)}</option>)}
          </select>
        </label>
        <button type="button" className="btn" disabled={!canAdd} onClick={() => chosen && onAdd({ driver, lap: chosen.n })}>Add lap</button>
        <button type="button" className="btn btn-quiet" disabled={!best || full || picks.some((p) => pickKey(p) === `${driver}:${best.n}`)}
          onClick={() => best && onAdd({ driver, lap: best.n })}>
          Add fastest lap{best ? ` (${best.n})` : ""}
        </button>
      </div>
      {full && <p className="muted small">{MAX_LAPS} laps is the most that can be told apart by colour. Remove one to add another.</p>}
    </div>
  );
}
