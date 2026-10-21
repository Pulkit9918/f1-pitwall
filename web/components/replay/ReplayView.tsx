"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { predictionAt } from "@/lib/analysis";
import { MAX_COMPARED } from "@/lib/colors";
import { useAnalysis } from "@/lib/data";
import { sessionLabel } from "@/lib/format";
import { assignSlots, driverOrder, maxLap, toggleDriver } from "@/lib/race";
import {
  buildLapIndex,
  driverFacts,
  gapsToDriver,
  lapEnds,
  lapsDoneAt,
  lapStartTime,
  leaderLap,
  qualiBoard,
  raceBoard,
  raceStart,
  statusAt,
  timeBands,
  timingRows,
  type CarState,
  type Replay,
} from "@/lib/replay";
import type { SessionDoc } from "@/lib/types";
import { loadUnits, saveUnits, type Units } from "@/lib/units";
import { SPEEDS, usePlayback } from "@/lib/usePlayback";
import { LapHistory } from "./LapHistory";
import { MessageFeed } from "./MessageFeed";
import { ReplayBoard, type Prediction } from "./ReplayBoard";
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
  const [tab, setTab] = useState<"timing" | "laps" | "messages">("timing");
  const [units, setUnits] = useState<Units>("metric");
  useEffect(() => setUnits(loadUnits()), []);
  const chooseUnits = (u: Units) => {
    setUnits(u);
    saveUnits(u);
  };
  const analysisLoad = useAnalysis(kind === "race" && (s.session_code === "R" || s.session_code === "S") ? s.session_key : null);
  const analysisDoc = analysisLoad.state === "ready" ? analysisLoad.data : null;
  const screenRef = useRef<HTMLDivElement>(null);
  const [fullscreen, setFullscreen] = useState(false);
  useEffect(() => {
    const onChange = () => setFullscreen(document.fullscreenElement === screenRef.current && screenRef.current !== null);
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);
  const toggleFullscreen = useCallback(() => {
    const el = screenRef.current;
    if (!el) return;
    if (document.fullscreenElement) void document.exitFullscreen();
    else if (el.requestFullscreen) void el.requestFullscreen();
  }, []);

  function toggle(code: string) {
    const picked = slots.filter((x): x is string => x !== null);
    setSlots(assignSlots(slots, toggleDriver(picked, code, MAX_COMPARED), MAX_COMPARED));
  }

  const board = useMemo(() => (kind === "race" ? raceBoard(replay, facts, play.slow, { total, start: clock0 }) : qualiBoard(facts, play.slow)), [kind, replay, facts, play.slow, total, clock0]);
  const states = useMemo(() => new Map<string, CarState>(board.map((r) => [r.code, r.state])), [board]);
  const positions = useMemo(() => new Map<string, number>(board.map((r) => [r.code, r.pos])), [board]);
  const timing = useMemo(() => timingRows(idx, board.map((r) => r.code), play.slow), [idx, board, play.slow]);
  const lap = leaderLap(ends, play.slow, total);
  const selected = slots.find((c): c is string => c !== null) ?? null;
  const gapsToSelected = useMemo(
    () => (kind === "race" && selected ? gapsToDriver(replay, board, play.slow, selected, clock0) : null),
    [kind, selected, replay, board, play.slow, clock0],
  );
  const predictions = useMemo(() => {
    if (!analysisDoc) return null;
    const out = new Map<string, Prediction>();
    for (const row of board) {
      const done = lapsDoneAt(facts.get(row.code)?.recs ?? [], play.slow);
      const p = predictionAt(analysisDoc, row.code, done);
      if (p) out.set(row.code, p);
    }
    return out;
  }, [analysisDoc, board, facts, play.slow]);
  const status = statusAt(replay.file, play.slow);
  const jumpToLap = useCallback(
    (n: number) => {
      const ts = lapStartTime(ends, n, clock0);
      if (ts != null) play.seek(ts);
    },
    [ends, clock0, play],
  );

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

      <div className="rp-units" role="group" aria-label="Units">
        <span className="muted small">Units</span>
        <button type="button" className={`chip${units === "metric" ? " chip-on" : ""}`} aria-pressed={units === "metric"} onClick={() => chooseUnits("metric")}>Metric</button>
        <button type="button" className={`chip${units === "imperial" ? " chip-on" : ""}`} aria-pressed={units === "imperial"} onClick={() => chooseUnits("imperial")}>Imperial</button>
      </div>

      <div ref={screenRef} className="rp-screen">
      <StatusStrip replay={replay} t={play.slow} kind={kind} lap={lap} totalLaps={total} clock={play.slow - clock0} units={units} />

      <div className="rp-stage">
        <ReplayMap replay={replay} t={play.t} states={states} leader={board[0]?.code ?? null} slots={slots} onToggle={toggle} status={status} />
        <ReplayBoard rows={board} kind={kind} slots={slots} teams={replay.teams} onToggle={toggle} gapsToSelected={gapsToSelected} selected={selected} predictions={predictions} />
      </div>

      <Transport
        raceStart={kind === "race" ? clock0 : undefined}
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
        totalLaps={kind === "race" ? total : undefined}
        onLap={kind === "race" ? jumpToLap : undefined}
        onFullscreen={typeof document !== "undefined" && document.fullscreenEnabled ? toggleFullscreen : undefined}
        fullscreen={fullscreen}
      />
      <p className="axis-caption rp-keys">Space plays or pauses. Left and right arrows skip 5 seconds, with Shift 30. Up and down change speed.</p>
      </div>

      <div className="rp-block">
        <h2>Drivers</h2>
        <TelemetryCards replay={replay} t={play.t} rows={board} kind={kind} slots={slots} units={units} />
      </div>

      <div className="rp-block">
        <div className="rp-tabs" role="tablist" aria-label="Details">
          <button type="button" role="tab" id="tab-timing" aria-selected={tab === "timing"} aria-controls="panel-timing" className={tab === "timing" ? "on" : ""} onClick={() => setTab("timing")}>Timing</button>
          {kind === "race" && (
            <button type="button" role="tab" id="tab-laps" aria-selected={tab === "laps"} aria-controls="panel-laps" className={tab === "laps" ? "on" : ""} onClick={() => setTab("laps")}>Lap history</button>
          )}
          <button type="button" role="tab" id="tab-messages" aria-selected={tab === "messages"} aria-controls="panel-messages" className={tab === "messages" ? "on" : ""} onClick={() => setTab("messages")}>Race control</button>
        </div>
        {tab === "timing" ? (
          <div role="tabpanel" id="panel-timing" aria-labelledby="tab-timing">
            <TimingTable rows={timing} idx={idx} t={play.slow} positions={positions} />
          </div>
        ) : tab === "laps" ? (
          <div role="tabpanel" id="panel-laps" aria-labelledby="tab-laps">
            <LapHistory idx={idx} slots={slots} t={play.slow} />
          </div>
        ) : (
          <div role="tabpanel" id="panel-messages" aria-labelledby="tab-messages">
            <MessageFeed replay={replay} t={play.slow} clock0={clock0} />
          </div>
        )}
      </div>
      <p className="axis-caption">
        Dot colours are the teams' own; a dark centre marks a team's second car, and a ring in blue, orange or green marks a selected driver
        and the card that goes with them. 
      </p>
    </>
  );
}
