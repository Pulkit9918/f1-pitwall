"use client";

import { useState } from "react";
import { CompoundChip } from "@/components/CompoundChip";
import { DRIVER_COLORS, teamFill } from "@/lib/colors";
import { fmtLap } from "@/lib/format";
import type { BoardRow, TeamInfo } from "@/lib/replay";

export function ReplayBoard({
  rows,
  kind,
  slots,
  teams,
  onToggle,
}: {
  rows: BoardRow[];
  kind: "race" | "quali";
  slots: (string | null)[];
  teams: Record<string, TeamInfo>;
  onToggle: (code: string) => void;
}) {
  const [mode, setMode] = useState<"leader" | "interval">("leader");
  const full = slots.every((s) => s !== null);
  return (
    <div className="rp-board-wrap">
      <div className="rp-board-head">
        <h2>{kind === "race" ? "Order" : "Fastest laps"}</h2>
        {kind === "race" && (
          <button type="button" className="link-button" onClick={() => setMode(mode === "leader" ? "interval" : "leader")}>
            {mode === "leader" ? "Show gap to car ahead" : "Show gap to leader"}
          </button>
        )}
      </div>
      <ol className="rp-board" aria-label="Running order. Select up to three drivers.">
        {rows.map((r) => {
          const slot = slots.indexOf(r.code);
          const on = slot >= 0;
          const blocked = !on && full;
          const gap = r.state === "out" ? "OUT" : kind === "quali" ? (r.best != null ? fmtLap(r.best) : "-") : mode === "leader" ? r.gapLeader : r.interval || r.gapLeader;
          return (
            <li key={r.code}>
              <button
                type="button"
                className={`rp-row${on ? " rp-row-on" : ""}`}
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
                </span>
                <span className={`rp-gap num${r.state === "out" ? " rp-out" : ""}`}>
                  {gap}
                  {kind === "quali" && r.gapLeader && r.gapLeader !== "Leader" && <small>{r.gapLeader}</small>}
                </span>
                <span className="rp-pit">{r.state === "pit" ? "PIT" : ""}</span>
                <span className="rp-tyre">
                  <CompoundChip compound={r.tyre.compound} />
                  <span className="num rp-age">{r.tyre.life ?? ""}</span>
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
