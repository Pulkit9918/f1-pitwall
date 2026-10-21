"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { Ready } from "@/components/State";
import { useSessions } from "@/lib/data";
import { isPractice, sessionLabel } from "@/lib/format";
import type { SessionMeta } from "@/lib/types";

const TYPES = [
  { id: "all", label: "All" },
  { id: "race", label: "Races", test: (s: SessionMeta) => s.session_code === "R" },
  { id: "quali", label: "Qualifying", test: (s: SessionMeta) => s.session_code === "Q" },
  { id: "sprint", label: "Sprints", test: (s: SessionMeta) => ["S", "SQ", "SS"].includes(s.session_code) },
  { id: "practice", label: "Practice", test: (s: SessionMeta) => isPractice(s.session_code) },
];

function Browser({ sessions }: { sessions: SessionMeta[] }) {
  const years = useMemo(() => [...new Set(sessions.map((s) => s.year))].sort((a, b) => b - a), [sessions]);
  const [year, setYear] = useState(years[0]);
  const [type, setType] = useState("all");

  const rounds = useMemo(() => {
    const test = TYPES.find((t) => t.id === type)?.test;
    const byRound = new Map<number, SessionMeta[]>();
    for (const s of sessions) {
      if (s.year !== year || !s.has_laps || (test && !test(s))) continue;
      (byRound.get(s.round) ?? byRound.set(s.round, []).get(s.round)!).push(s);
    }
    return [...byRound.entries()].sort((a, b) => a[0] - b[0]);
  }, [sessions, year, type]);

  return (
    <>
      <div className="filters">
        <div role="group" aria-label="Season" className="chips">
          {years.map((y) => (
            <button key={y} type="button" className={`chip${y === year ? " chip-on" : ""}`} aria-pressed={y === year} onClick={() => setYear(y)}>{y}</button>
          ))}
        </div>
        <div role="group" aria-label="Session type" className="chips">
          {TYPES.map((t) => (
            <button key={t.id} type="button" className={`chip${t.id === type ? " chip-on" : ""}`} aria-pressed={t.id === type} onClick={() => setType(t.id)}>{t.label}</button>
          ))}
        </div>
      </div>
      {rounds.length === 0 && <p className="muted">No sessions match. Try another season or session type.</p>}
      <ol className="rounds">
        {rounds.map(([round, list]) => (
          <li key={round}>
            <div className="round-title">
              <span className="round-no num">R{String(round).padStart(2, "0")}</span>
              <div>
                <h2>{list[0].event}</h2>
                <p className="muted small">{[list[0].circuit_name, list[0].country].filter(Boolean).join(", ")}</p>
              </div>
            </div>
            <ul className="session-links">
              {list.map((s) => (
                <li key={s.session_key}>
                  <Link href={`/race?key=${encodeURIComponent(s.session_key)}`}>{sessionLabel(s.session_code, s.session_name)}</Link>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ol>
    </>
  );
}

export default function SessionsPage() {
  const load = useSessions();
  return (
    <>
      <section className="hero hero-small">
        <h1>Sessions</h1>
        <p className="lede">Every session with lap data. Open one for its tyre strategy, lap times, running order and pit stops.</p>
      </section>
      <Ready load={load} label="Loading sessions">{({ sessions }) => <Browser sessions={sessions} />}</Ready>
    </>
  );
}
