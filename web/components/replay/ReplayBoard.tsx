"use client";

import { useState } from "react";
import { CompoundChip } from "@/components/CompoundChip";
import { DRIVER_COLORS, teamFill } from "@/lib/colors";
import { fmtLap } from "@/lib/format";
import type { Regime } from "@/lib/analysis";
import { frozenAt, type BoardRow, type Span, type TeamInfo } from "@/lib/replay";

export type GapMode = "leader" | "interval" | "driver";
export type Prediction = { position: number | null; regime: Regime };
export type RowExtra = { history: string[]; pit: number | null };

export function ReplayBoard({
  rows,
  kind,
  slots,
  teams,
  onToggle,
  gapsToSelected,
  selected,
  predictions,
  frozen,
  now,
  extras,
  fastest,
}: {
  rows: BoardRow[];
  kind: "race" | "quali";
  slots: (string | null)[];
  teams: Record<string, TeamInfo>;
  onToggle: (code: string) => void;
  gapsToSelected: Map<string, string> | null;
  selected: string | null;
  predictions: Map<string, Prediction> | null;
  frozen: Map<string, Span[]>;
  now: number;
  extras: Map<string, RowExtra>;
  fastest: string | null;
}) {
  const [chosen, setMode] = useState<GapMode>("leader");
  const [showPred, setShowPred] = useState(false);
  const mode: GapMode = chosen === "driver" && !(selected && gapsToSelected) ? "leader" : chosen;
  const pred = showPred && predictions ? predictions : null;
  const full = slots.every((s) => s !== null);
  return (
    <div className="rp-board-wrap">
      <div className="rp-board-head">
        <h2>{kind === "race" ? "Order" : "Fastest laps"}</h2>
      </div>
      {kind === "race" && (
        <div className="rp-board-opts">
          <div role="group" aria-label="Gap shown" className="chips">
            <button type="button" className={`chip${mode === "leader" ? " chip-on" : ""}`} aria-pressed={mode === "leader"} onClick={() => setMode("leader")}>To leader</button>
            <button type="button" className={`chip${mode === "interval" ? " chip-on" : ""}`} aria-pressed={mode === "interval"} onClick={() => setMode("interval")}>To car ahead</button>
            <button
              type="button" className={`chip${mode === "driver" ? " chip-on" : ""}`} aria-pressed={mode === "driver"}
              disabled={!selected} title={selected ? undefined : "Select a driver in the list first"} onClick={() => setMode("driver")}
            >
              {selected ? `To ${selected}` : "To a driver"}
            </button>
          </div>
          {predictions && (
            <label className="rp-check">
              <input type="checkbox" checked={showPred} onChange={(e) => setShowPred(e.target.checked)} /> Pit prediction
            </label>
          )}
        </div>
      )}
      <ol className="rp-board" aria-label="Running order. Select up to three drivers.">
        {rows.map((r) => {
          const slot = slots.indexOf(r.code);
          const on = slot >= 0;
          const blocked = !on && full;
          const lost = r.state !== "out" && frozenAt(frozen.get(r.code), now);
          const ex = extras.get(r.code);
          const gap = r.state === "out" ? "OUT" : kind === "quali" ? (r.best != null ? fmtLap(r.best) : "-") : mode === "leader" ? r.gapLeader : mode === "driver" ? gapsToSelected?.get(r.code) ?? "" : r.interval || r.gapLeader;
          return (
            <li key={r.code}>
              <button
                type="button"
                className={`rp-row${on ? " rp-row-on" : ""}${pred ? " rp-row-pred" : ""}`}
                aria-pressed={on}
                aria-disabled={blocked}
                title={blocked ? "Three drivers are selected; remove one first" : undefined}
                onClick={() => !blocked && onToggle(r.code)}
              >
                <span className={`rp-bar${teams[r.code]?.second ? " rp-bar-2" : ""}`} style={{ backgroundColor: teamFill(teams[r.code]?.color) ?? "transparent" }} />
                <span className="rp-pos num">{r.pos}</span>
                <span className="rp-code" title={teams[r.code]?.name ?? undefined}>
                  {r.code}
                  {on && <span className="rp-slot" style={{ background: DRIVER_COLORS[slot] }} aria-hidden="true" />}
                  {fastest === r.code && <span className="rp-fl" title="Fastest lap so far">FL</span>}
                </span>
                <span className={`rp-gap num${r.state === "out" ? " rp-out" : ""}${mode === "interval" && r.intervalS != null && r.intervalS < 1 ? " rp-close" : ""}`}>
                  {gap}
                  {kind === "quali" && r.gapLeader && r.gapLeader !== "Leader" && <small>{r.gapLeader}</small>}
                </span>
                {pred && (() => {
                  const p = pred.get(r.code);
                  const low = p?.regime === "sc" || p?.regime === "vsc";
                  return (
                    <span className="rp-predcell num" title={p?.position != null ? `Would rejoin in P${p.position} if pitting at the end of the lap just finished${low ? " (low confidence under a safety car or VSC)" : ""}` : "No prediction"}>
                      {p?.position != null ? `P${p.position}${low ? "*" : ""}` : "-"}
                    </span>
                  );
                })()}
                <span className="rp-pit" title={lost && r.state !== "pit" ? "Position data stopped; the dot is not where the car is" : undefined}>
                  {r.state === "pit" ? (ex?.pit != null ? `PIT ${Math.floor(ex.pit)}s` : "PIT") : lost ? "!" : ""}
                  {lost && r.state !== "pit" && <span className="sr-only"> position data lost</span>}
                </span>
                <span className="rp-tyre">
                  {ex && ex.history.length > 0 && (
                    <span className="rp-hist" title={`Earlier tyres: ${ex.history.join(", ")}`}>
                      {ex.history.map((c, i) => <CompoundChip key={i} compound={c} />)}
                    </span>
                  )}
                  <CompoundChip compound={r.tyre.compound} />
                  <span className="num rp-age">{r.tyre.life ?? ""}</span>
                </span>
              </button>
            </li>
          );
        })}
      </ol>
      {pred && <p className="axis-caption">Pit prediction: the place each driver would rejoin in if they pitted at the end of the lap they just finished. * is low confidence (safety car or VSC).</p>}
      {[...frozen.values()].some((s) => frozenAt(s, now)) && (
        <p className="axis-caption">! marks a car whose position data stopped changing while the lap table shows it still racing. Its dot stays where the data stopped, so between lap ends its place in the order and its gaps may be off.</p>
      )}
    </div>
  );
}
