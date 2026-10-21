"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { MAX_COMPARED } from "@/lib/colors";
import { sessionLabel } from "@/lib/format";
import { assignSlots, driverOrder, maxLap, toggleDriver } from "@/lib/race";
import {
  buildLapIndex,
  driverFacts,
  lapEnds,
  leaderLap,
  qualiBoard,
  raceBoard,
  raceStart,
  timeBands,
  timingRows,
  type CarState,
  type Replay,
} from "@/lib/replay";
import type { SessionDoc } from "@/lib/types";
import { SPEEDS, usePlayback } from "@/lib/usePlayback";
import { MessageFeed } from "./MessageFeed";
import { ReplayBoard } from "./ReplayBoard";
import { ReplayMap } from "./ReplayMap";
import { StatusStrip } from "./StatusStrip";
import { TelemetryCards } from "./TelemetryCards";
import { TimingTable } from "./TimingTable";
import { Transport } from "./Transport";

export function ReplayView({ doc, replay }: { doc: SessionDoc; replay: Replay }) {
  const kind = replay.file.kind;
  const s = doc.session;
  const idx = useMemo(() => buildLapIndex(doc), [doc]);
  const facts = useMemo(() => driverFacts(idx), [idx]);
  const ends = useMemo(() => lapEnds(idx), [idx]);
  const total = maxLap(doc);
  const clock0 = useMemo(() => raceStart(idx, replay.t0), [idx, replay.t0]);
  const bands = useMemo(() => timeBands(replay, doc), [replay, doc]);
  const order = useMemo(() => driverOrder(doc), [doc]);
  const ticks = useMemo(() => {
    if (kind !== "race") return [];
    const out: { t: number; label: string }[] = [];
    for (let n = 10; n < total; n += 10) if (ends[n - 2] !== undefined) out.push({ t: ends[n - 2], label: String(n) });
    return out;
  }, [kind, ends, total]);

  const play = usePlayback(replay.t0, replay.end, Math.max(replay.t0, clock0 - 10));
  const [slots, setSlots] = useState<(string | null)[]>(() =>
    assignSlots(Array(MAX_COMPARED).fill(null), order.filter((c) => replay.file.drivers[c]).slice(0, MAX_COMPARED), MAX_COMPARED),
  );
  const [tab, setTab] = useState<"timing" | "messages">("timing");

  function toggle(code: string) {
    const picked = slots.filter((x): x is string => x !== null);
    setSlots(assignSlots(slots, toggleDriver(picked, code, MAX_COMPARED), MAX_COMPARED));
  }

  const board = useMemo(() => (kind === "race" ? raceBoard(replay, facts, play.slow, { total, start: clock0 }) : qualiBoard(facts, play.slow)), [kind, replay, facts, play.slow, total, clock0]);
  const states = useMemo(() => new Map<string, CarState>(board.map((r) => [r.code, r.state])), [board]);
  const positions = useMemo(() => new Map<string, number>(board.map((r) => [r.code, r.pos])), [board]);
  const timing = useMemo(() => timingRows(idx, board.map((r) => r.code), play.slow), [idx, board, play.slow]);
  const lap = leaderLap(ends, play.slow, total);

  // Space plays and pauses, the arrow keys skip and change speed. Buttons and the slider keep their own keys.
  const { toggle: togglePlay, skip, setSpeed, speed } = play;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      const tag = el?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === " " && tag !== "BUTTON") {
        e.preventDefault();
        togglePlay();
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        skip(e.shiftKey ? -30 : -5);
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        skip(e.shiftKey ? 30 : 5);
      } else if (e.key === "ArrowUp" || e.key === "ArrowDown") {
        e.preventDefault();
        const i = SPEEDS.indexOf(speed);
        setSpeed(SPEEDS[Math.max(0, Math.min(SPEEDS.length - 1, i + (e.key === "ArrowUp" ? 1 : -1)))]);
      }
    };
    // After a mouse click, a button gives up focus so that Space still plays and pauses (a keyboard click has detail 0).
    const onClick = (e: MouseEvent) => {
      const el = e.target instanceof Element ? e.target.closest("button") : null;
      if (el && e.detail > 0) el.blur();
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("click", onClick);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("click", onClick);
    };
  }, [togglePlay, skip, setSpeed, speed]);

  return (
    <>
      <div className="hero hero-small">
        <p className="crumb">
          <Link href="/sessions">Sessions</Link> / <Link href={`/race?key=${encodeURIComponent(s.session_key)}`}>{s.event}, {s.year}</Link>
        </p>
        <h1>{s.event}, {s.year}: replay</h1>
        <p className="lede">{sessionLabel(s.session_code, s.session_name)}. Cars move along the circuit once a second, drawn from the timing data.</p>
      </div>

      <StatusStrip replay={replay} t={play.slow} kind={kind} lap={lap} totalLaps={total} clock={play.slow - clock0} />

      <div className="rp-stage">
        <ReplayMap replay={replay} t={play.t} states={states} leader={board[0]?.code ?? null} slots={slots} onToggle={toggle} />
        <ReplayBoard rows={board} kind={kind} slots={slots} teams={replay.teams} onToggle={toggle} />
      </div>

      <Transport
        start={replay.t0}
        end={replay.end}
        t={play.t}
        clock0={clock0}
        playing={play.playing}
        speed={play.speed}
        bands={bands}
        ticks={ticks}
        onToggle={play.toggle}
        onSeek={play.seek}
        onSkip={play.skip}
        onSpeed={play.setSpeed}
      />
      <p className="axis-caption rp-keys">Space plays or pauses. Left and right arrows skip 5 seconds, with Shift 30. Up and down change speed.</p>

      <div className="rp-block">
        <h2>Drivers</h2>
        <TelemetryCards replay={replay} t={play.t} rows={board} kind={kind} slots={slots} />
      </div>

      <div className="rp-block">
        <div className="rp-tabs" role="tablist" aria-label="Details">
          <button type="button" role="tab" id="tab-timing" aria-selected={tab === "timing"} aria-controls="panel-timing" className={tab === "timing" ? "on" : ""} onClick={() => setTab("timing")}>Timing</button>
          <button type="button" role="tab" id="tab-messages" aria-selected={tab === "messages"} aria-controls="panel-messages" className={tab === "messages" ? "on" : ""} onClick={() => setTab("messages")}>Race control</button>
        </div>
        {tab === "timing" ? (
          <div role="tabpanel" id="panel-timing" aria-labelledby="tab-timing">
            <TimingTable rows={timing} idx={idx} t={play.slow} positions={positions} />
          </div>
        ) : (
          <div role="tabpanel" id="panel-messages" aria-labelledby="tab-messages">
            <MessageFeed replay={replay} t={play.slow} clock0={clock0} />
          </div>
        )}
      </div>
      <p className="axis-caption">
        Dot colours are the teams' own; a dark centre marks a team's second car, and a ring in blue, orange or green marks a selected driver
        and the card that goes with them. Positions come from snapping each car's x and y to one lap of the circuit, so cars in the pit lane are drawn on the track. Gaps are
        the time since the car ahead was at the same point. Wind is shown in metres per second, as FastF1 documents it; neither this nor the
        DRS reading has been checked against an outside source.
      </p>
    </>
  );
}
