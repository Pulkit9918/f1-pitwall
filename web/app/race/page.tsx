"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { DriverPicker } from "@/components/DriverPicker";
import { LapChart } from "@/components/LapChart";
import { PitTable } from "@/components/PitTable";
import { PositionChart } from "@/components/PositionChart";
import { ReplayLink } from "@/components/ReplayLink";
import { Loading, Ready } from "@/components/State";
import { StrategyChart } from "@/components/StrategyChart";
import { MAX_COMPARED } from "@/lib/colors";
import { useSession } from "@/lib/data";
import { isPractice, sessionLabel } from "@/lib/format";
import { assignSlots, driverOrder, hasPositions, maxLap, pitRows, toggleDriver } from "@/lib/race";
import type { SessionDoc } from "@/lib/types";

function RaceView({ doc }: { doc: SessionDoc }) {
  const order = useMemo(() => driverOrder(doc), [doc]);
  const pits = useMemo(() => pitRows(doc), [doc]);
  const [slots, setSlots] = useState<(string | null)[]>(() => assignSlots(Array(MAX_COMPARED).fill(null), order.slice(0, MAX_COMPARED), MAX_COMPARED));
  const s = doc.session;
  const periods = doc.race_control_periods.length;

  function toggle(code: string) {
    const selected = slots.filter((x): x is string => x !== null);
    setSlots(assignSlots(slots, toggleDriver(selected, code, MAX_COMPARED), MAX_COMPARED));
  }

  return (
    <>
      <section className="hero hero-small">
        <p className="crumb"><Link href="/sessions">Sessions</Link></p>
        <h1>{s.event}, {s.year}</h1>
        <p className="lede">
          {sessionLabel(s.session_code, s.session_name)}, round {s.round}.{" "}
          {[s.circuit_name, s.country].filter(Boolean).join(", ")}
        </p>
        <ReplayLink sessionKey={s.session_key} />
        <dl className="facts">
          <div><dt>Laps</dt><dd className="num">{maxLap(doc)}</dd></div>
          <div><dt>Drivers</dt><dd className="num">{order.length}</dd></div>
          <div><dt>Pit stops</dt><dd className="num">{pits.length}</dd></div>
          <div><dt>Safety car, VSC and red flag periods</dt><dd className="num">{periods}</dd></div>
        </dl>
      </section>

      <section aria-labelledby="strategy">
        <h2 id="strategy">Tyre strategy</h2>
        <StrategyChart doc={doc} />
      </section>

      <section aria-labelledby="compare">
        <h2 id="compare">Compare drivers</h2>
        <p className="muted small">Pick up to three. Their colours stay with them while they are selected.</p>
        <DriverPicker order={order} slots={slots} onToggle={toggle} />
        <h3>Lap times</h3>
        <LapChart doc={doc} slots={slots} />
        {hasPositions(doc) ? (
          <>
            <h3>Running order</h3>
            <PositionChart doc={doc} slots={slots} />
          </>
        ) : (
          <p className="muted small">{isPractice(s.session_code) ? "Practice sessions have no running order." : "This session has no recorded running order."}</p>
        )}
      </section>

      <section aria-labelledby="pits">
        <h2 id="pits">Pit stops</h2>
        <PitTable stops={pits} />
      </section>
    </>
  );
}

function RaceInner() {
  const key = useSearchParams().get("key");
  const load = useSession(key);
  if (!key) {
    return (
      <section className="hero hero-small">
        <h1>No session chosen</h1>
        <p className="lede">Pick one from the <Link href="/sessions">sessions list</Link>.</p>
      </section>
    );
  }
  if (load.state === "error" && load.message.startsWith("404")) {
    return (
      <section className="hero hero-small">
        <h1>Session not found</h1>
        <p className="lede">There is no data for <code>{key}</code>. Pick one from the <Link href="/sessions">sessions list</Link>.</p>
      </section>
    );
  }
  return <Ready load={load} label="Loading the session">{(doc) => <RaceView key={doc.session.session_key} doc={doc} />}</Ready>;
}

export default function RacePage() {
  return (
    <Suspense fallback={<Loading />}>
      <RaceInner />
    </Suspense>
  );
}
