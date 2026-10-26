"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import { groupWeekends, pickYear, type WeekendSession } from "@/lib/weekends";
import "./sessionPicker.css";

// A year at a time, one row per race weekend, one link for each session that has data. The year stays in the address
// (?year=2024), so going back from a session returns to the same list.
export function SessionPicker({ sessions, base, codes, empty }: { sessions: WeekendSession[]; base: string; codes?: string[]; empty?: string }) {
  const groups = useMemo(() => groupWeekends(sessions, codes), [sessions, codes]);
  const wanted = useSearchParams().get("year");
  const [year, setYear] = useState<number | null>(() => pickYear(groups, wanted));
  const current = groups.find((g) => g.year === year) ?? groups[0];
  if (!current) return <p className="muted">{empty ?? "No sessions yet."}</p>;

  const choose = (y: number) => {
    setYear(y);
    try {
      window.history.replaceState(null, "", `?year=${y}`);
    } catch {
      /* the list still works without the address */
    }
  };

  return (
    <section aria-label="Sessions">
      <div className="year-tabs">
        {groups.map((g) => (
          <button key={g.year} type="button" className="year-tab" aria-pressed={g.year === current.year} onClick={() => choose(g.year)}>
            {g.year}
          </button>
        ))}
      </div>
      <p className="muted small weekend-count">{current.weekends.length} race {current.weekends.length === 1 ? "weekend" : "weekends"} in {current.year}</p>
      <ol className="weekends">
        {current.weekends.map((w) => (
          <li key={`${w.year}-${w.round}`} className="weekend">
            <span className="weekend-name">{w.event}</span>
            <ul className="weekend-sessions">
              {w.sessions.map((s) => (
                <li key={s.key}>
                  <Link href={`${base}?key=${encodeURIComponent(s.key)}`}>{s.label}</Link>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ol>
    </section>
  );
}
