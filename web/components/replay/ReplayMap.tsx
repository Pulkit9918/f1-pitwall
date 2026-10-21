"use client";

import { useMemo } from "react";
import { DRIVER_COLORS, teamFill } from "@/lib/colors";
import { cumAt, hasData, trackPoint, type CarState, type Replay } from "@/lib/replay";

const PAD = 36;

export function ReplayMap({
  replay,
  t,
  states,
  leader,
  slots,
  onToggle,
}: {
  replay: Replay;
  t: number;
  states: Map<string, CarState>;
  leader: string | null;
  slots: (string | null)[];
  onToggle: (code: string) => void;
}) {
  const { w, h, pts } = replay.file.track;
  const outline = useMemo(() => `M${pts.map((p) => p.join(",")).join("L")}Z`, [pts]);
  const finish = useMemo(() => {
    const [a, b] = pts[0];
    const [c, d] = pts[1];
    const len = Math.hypot(c - a, d - b) || 1;
    const nx = (-(d - b) / len) * 15;
    const ny = ((c - a) / len) * 15;
    return { x1: a - nx, y1: b - ny, x2: a + nx, y2: b + ny };
  }, [pts]);

  const cars = replay.codes
    .filter((c) => hasData(replay, c, t) && states.get(c) !== "out")
    .map((c) => {
      const [x, y] = trackPoint(pts, cumAt(replay, c, t));
      return { c, x, y, slot: slots.indexOf(c) };
    })
    .sort((a, b) => Number(a.slot >= 0) - Number(b.slot >= 0) || Number(a.c === leader) - Number(b.c === leader));

  return (
    <svg
      className="rp-map"
      viewBox={`${-PAD} ${-PAD} ${w + PAD * 2} ${h + PAD * 2}`}
      role="img"
      aria-label={`Track map with ${cars.length} cars. The leaderboard lists them in order.`}
    >
      <path d={outline} className="rp-road-edge" />
      <path d={outline} className="rp-road" />
      <line {...finish} className="rp-finish" />
      {cars.map(({ c, x, y, slot }) => {
        const picked = slot >= 0;
        const pit = states.get(c) === "pit";
        const team = replay.teams[c];
        const color = teamFill(team?.color);
        // With a team colour the dot is that colour; a pit car is a ring of it, the leader has a light rim, and a
        // selected driver gets a thick ring in the colour of their card below. Without one, the plain grey dots are used.
        const style = color
          ? {
              fill: pit ? "var(--ground)" : color,
              stroke: picked ? DRIVER_COLORS[slot] : pit ? color : c === leader ? "var(--ink)" : "var(--ground)",
              strokeWidth: picked ? 5 : pit || c === leader ? 3.5 : 2.5,
            }
          : picked
            ? { fill: DRIVER_COLORS[slot], stroke: "var(--ink)" }
            : undefined;
        return (
          <g key={c} transform={`translate(${x},${y})`} className="rp-car" onClick={() => onToggle(c)}>
            <circle
              r={picked ? 13 : 9}
              className={`rp-dot${!color && c === leader ? " rp-dot-lead" : ""}${!color && pit ? " rp-dot-pit" : ""}`}
              style={style}
            />
            {color && team?.second && <circle r={picked ? 5 : 3.5} className="rp-dot-second" style={pit ? { fill: color } : undefined} />}
            <text y={picked ? -19 : -14} textAnchor="middle" className={picked ? "rp-tag rp-tag-on" : "rp-tag"}>
              {c}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
