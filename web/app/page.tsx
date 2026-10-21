"use client";

import Link from "next/link";
import { Ready } from "@/components/State";
import { StrategyChart } from "@/components/StrategyChart";
import { useCircuits, useManifest, useSession, useSessions } from "@/lib/data";
import type { Circuit, SessionMeta } from "@/lib/types";

function latestRace(sessions: SessionMeta[]): SessionMeta | null {
  const races = sessions.filter((s) => s.session_code === "R" && s.has_laps);
  return races.length ? races[races.length - 1] : null;
}

function pitLossSentence(circuits: Circuit[]): string | null {
  const ok = circuits.filter((c) => c.pit_loss?.is_reliable && c.pit_loss.median_pit_loss_s != null);
  if (ok.length < 2) return null;
  const sorted = [...ok].sort((a, b) => a.pit_loss!.median_pit_loss_s! - b.pit_loss!.median_pit_loss_s!);
  const lo = sorted[0];
  const hi = sorted[sorted.length - 1];
  return `A pit stop costs ${lo.pit_loss!.median_pit_loss_s!.toFixed(1)} seconds at ${lo.circuit_name} and ${hi.pit_loss!.median_pit_loss_s!.toFixed(1)} at ${hi.circuit_name}.`;
}

function Hero() {
  const manifest = useManifest();
  const sessions = useSessions();
  const circuits = useCircuits();
  const latest = sessions.state === "ready" ? latestRace(sessions.data.sessions) : null;
  const doc = useSession(latest?.session_key ?? null);

  const first = manifest.state === "ready" ? manifest.data.from_year : 2022;
  const count = manifest.state === "ready" ? manifest.data.sessions : null;
  const sentence = circuits.state === "ready" ? pitLossSentence(circuits.data.circuits) : null;

  return (
    <>
      <section className="hero">
        <h1>Pit-wall analytics for every race since {first}</h1>
        <p className="lede">
          Tyre strategies, pit-stop costs and race-control periods{count ? `, measured from ${count} sessions of timing data` : ""}.
          {sentence ? ` ${sentence}` : ""}
        </p>
      </section>

      <section aria-labelledby="latest">
        <div className="section-head">
          <h2 id="latest">{latest ? `${latest.event}, ${latest.year}` : "Latest race"}</h2>
          {latest && <Link href={`/race?key=${encodeURIComponent(latest.session_key)}`} className="more">Open this race</Link>}
        </div>
        <p className="muted small">Tyre strategy, in finishing order.</p>
        {sessions.state === "ready" && !latest && <p className="muted">There are no races with lap data yet.</p>}
        {sessions.state !== "ready" ? (
          <Ready load={sessions}>{() => null}</Ready>
        ) : (
          latest && <Ready load={doc} label="Loading the race">{(d) => <StrategyChart doc={d} compact />}</Ready>
        )}
      </section>

      <section aria-labelledby="where">
        <h2 id="where">Where to look</h2>
        <dl className="index">
          <div>
            <dt><Link href="/circuits">Circuits</Link></dt>
            <dd>What a pit stop costs at each track, and how fast each compound wears.</dd>
          </div>
          <div>
            <dt><Link href="/sessions">Sessions</Link></dt>
            <dd>Every race, qualifying, sprint and practice session, with its strategy, lap times and pit stops.</dd>
          </div>
          <div>
            <dt><a href="https://github.com/Pulkit9918/f1-pitwall#readme">Method and known gaps</a></dt>
            <dd>How the data is collected and checked, and where it is known to be wrong.</dd>
          </div>
        </dl>
      </section>
    </>
  );
}

export default function Home() {
  return <Hero />;
}
