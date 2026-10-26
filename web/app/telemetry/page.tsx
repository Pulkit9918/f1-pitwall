"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { LapPicker } from "@/components/LapPicker";
import { Loading, LoadError, Ready } from "@/components/State";
import { TraceChart, type Hover, type PanelSpec, type Series } from "@/components/TraceChart";
import { TRACE_COLORS, TRACE_DASH } from "@/lib/colors";
import { fmtLap, sessionLabel } from "@/lib/format";
import { useDriverFiles, useTraceIndex, useTraceSession } from "@/lib/traceData";
import {
  addPick, deltaTo, driversByPace, drawLaps, fastestLap, lapLabel, pickColors, pickKey, removePick,
  type DrawnLap, type Pick, type TraceSession,
} from "@/lib/traces";
import "./telemetry.css";

const sec = (v: number) => `${v > 0 ? "+" : v < 0 ? "-" : ""}${Math.abs(v).toFixed(3)} s`;
const PANELS: (PanelSpec & { channel: "speed" | "throttle" | "brake" | "gear" | "drs" | "delta" })[] = [
  { id: "delta", channel: "delta", title: "Time against the reference lap", unit: "seconds, above zero is behind", height: 190, symmetric: true, fmt: sec, tickFmt: (v) => `${v > 0 ? "+" : ""}${v}`, labels: true,
    caption: "How far each lap is ahead of or behind the reference lap at every point of the circuit. The line rises where a lap loses time and falls where it gains." },
  { id: "speed", channel: "speed", title: "Speed", unit: "km/h", height: 200, fmt: (v) => `${Math.round(v)} km/h`, tickFmt: (v) => `${v}` },
  { id: "throttle", channel: "throttle", title: "Throttle", unit: "percent", height: 100, domain: [0, 100], ticks: 2, fmt: (v) => `${Math.round(v)}%`, tickFmt: (v) => `${v}` },
  { id: "brake", channel: "brake", title: "Brake", unit: "on or off", height: 64, step: true, domain: [0, 1], ticks: 1, fmt: (v) => (v ? "on" : "off"), tickFmt: (v) => (v ? "on" : "off") },
  { id: "gear", channel: "gear", title: "Gear", unit: "", height: 110, step: true, domain: [1, 8], ticks: 7, fmt: (v) => `${v}`, tickFmt: (v) => `${v}` },
  { id: "drs", channel: "drs", title: "DRS", unit: "open or closed", height: 64, step: true, domain: [0, 1], ticks: 1, fmt: (v) => (v ? "open" : "closed"), tickFmt: (v) => (v ? "open" : "closed") },
];

function Compare({ session }: { session: TraceSession }) {
  const order = useMemo(() => driversByPace(session.drivers), [session]);
  const [picks, setPicks] = useState<Pick[]>(() =>
    order.slice(0, 2).flatMap((code) => {
      const best = fastestLap(session.drivers.find((d) => d.code === code)?.laps ?? []);
      return best ? [{ driver: code, lap: best.n }] : [];
    }),
  );
  const [slots, setSlots] = useState<Record<string, number>>(() => pickColors(picks, {}));
  const [ref, setRef] = useState<string>("");
  const [hover, setHover] = useState<Hover | null>(null);
  const { files, loading, error } = useDriverFiles(session.session_key, picks.map((p) => p.driver));

  const update = (next: Pick[]) => {
    setPicks(next);
    setSlots(pickColors(next, slots));
  };
  const refKey = picks.some((p) => pickKey(p) === ref) ? ref : picks[0] ? pickKey(picks[0]) : "";
  const drawn: DrawnLap[] = useMemo(() => drawLaps(picks, slots, session, files), [picks, slots, session, files]);
  const reference = drawn.find((d) => pickKey(d.pick) === refKey) ?? drawn[0];
  const timeOnly = drawn.filter((d) => d.lap.speed === null);

  const panels = PANELS.map((spec) => {
    const series: Series[] = [];
    for (const d of drawn) {
      const values = spec.channel === "delta" ? (reference ? deltaTo(reference.lap, d.lap) : null) : d.lap[spec.channel];
      if (values) series.push({ lap: d, values });
    }
    return { spec, series };
  }).filter((p) => p.series.length > 0);

  return (
    <>
      <section className="hero hero-small">
        <p className="crumb"><Link href="/telemetry">Telemetry</Link></p>
        <h1>{session.event}, {session.year}</h1>
        <p className="lede">
          {sessionLabel(session.session_code)}, round {session.round}. {[session.circuit_name, session.country].filter(Boolean).join(", ")}.
          Laps are lined up by distance round the track, so two laps can be compared corner by corner.
        </p>
        <p className="muted small">
          <Link href={`/race?key=${encodeURIComponent(session.session_key)}`}>Race analysis</Link>
        </p>
      </section>

      <section aria-labelledby="laps">
        <h2 id="laps">Laps</h2>
        <LapPicker session={session} order={order} picks={picks} slots={slots} refKey={refKey}
          onAdd={(p) => update(addPick(picks, p))} onRemove={(p) => update(removePick(picks, p))} onReference={(p) => setRef(pickKey(p))} />
        {drawn.length >= 2 && (
          <ul className="legend trace-legend" aria-label="Legend">
            {drawn.map((d) => (
              <li key={pickKey(d.pick)}>
                <svg width="26" height="10" aria-hidden="true"><line x1="0" x2="26" y1="5" y2="5" stroke={TRACE_COLORS[d.slot]} strokeWidth="2.5" strokeDasharray={TRACE_DASH[d.slot]} /></svg>
                {lapLabel(d.pick)}{d.meta?.t != null && <span className="num muted"> {fmtLap(d.meta.t)}</span>}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section aria-labelledby="traces">
        <h2 id="traces">Against distance</h2>
        {error && <LoadError message={error} />}
        {!error && loading && drawn.length === 0 && <Loading label="Loading the laps" />}
        {!error && !loading && picks.length === 0 && <p className="muted">Add a lap above to draw it.</p>}
        {timeOnly.length > 0 && (
          <p className="notice-inline">
            {timeOnly.map((d) => lapLabel(d.pick)).join(", ")} {timeOnly.length === 1 ? "has" : "have"} no speed, throttle, brake, gear or DRS lines: the speed channel
            did not agree with the car&apos;s positions on {timeOnly.length === 1 ? "that lap" : "those laps"}, so only the time delta is drawn.
          </p>
        )}
        <div className="trace-stack">
          {panels.map(({ spec, series }, i) => (
            <TraceChart key={spec.id} spec={spec} series={series} dist={session.dist} hover={hover} onHover={setHover} last={i === panels.length - 1} />
          ))}
        </div>
        {drawn.length > 0 && (
          <p className="axis-caption">
            Distance is measured along the car&apos;s position trace and scaled so that every lap covers the same track length ({Math.round(session.ref_length_m)} m here,
            from the measurements, not a surveyed figure). Each line has {session.points} points. DRS counts as open when the feed reports codes 10, 12 or 14.
          </p>
        )}
      </section>
    </>
  );
}

function SessionList() {
  const load = useTraceIndex();
  return (
    <>
      <section className="hero hero-small">
        <h1>Telemetry</h1>
        <p className="lede">
          Pick a race or sprint, then compare laps from any drivers against distance: speed, throttle, brake, gear, DRS and the time gained or lost at every point of the track.
        </p>
      </section>
      <Ready load={load} label="Loading sessions">
        {(idx) => {
          const years = [...new Set(idx.sessions.map((s) => s.year))].sort((a, b) => b - a);
          return (
            <>
              {years.map((y) => (
                <section key={y} aria-labelledby={`y${y}`}>
                  <h2 id={`y${y}`}>{y}</h2>
                  <ul className="session-links">
                    {idx.sessions.filter((s) => s.year === y).sort((a, b) => a.round - b.round || a.session_code.localeCompare(b.session_code)).map((s) => (
                      <li key={s.key}>
                        <Link href={`/telemetry?key=${encodeURIComponent(s.key)}`}>
                          {s.event}{s.session_code === "S" ? ", sprint" : ""} <span className="muted">{s.laps} laps</span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                </section>
              ))}
              {idx.sessions.length === 0 && <p className="muted">No session has telemetry traces yet. Run <code>python scripts/export_traces.py</code>.</p>}
            </>
          );
        }}
      </Ready>
    </>
  );
}

function TelemetryInner() {
  const key = useSearchParams().get("key");
  const session = useTraceSession(key);
  if (!key) return <SessionList />;
  if (session.state === "error" && session.message.startsWith("404")) {
    return (
      <section className="hero hero-small">
        <h1>No telemetry for this session</h1>
        <p className="lede">Traces cover races and sprints from 2024 on. <Link href="/telemetry">Choose another session</Link>.</p>
      </section>
    );
  }
  if (session.state === "error") return <LoadError message={session.message} />;
  if (session.state === "loading") return <Loading label="Loading the session" />;
  return <Compare key={session.data.session_key} session={session.data} />;
}

export default function TelemetryPage() {
  return (
    <Suspense fallback={<Loading />}>
      <TelemetryInner />
    </Suspense>
  );
}
