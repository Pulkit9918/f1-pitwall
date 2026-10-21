"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { DriverPicker } from "@/components/DriverPicker";
import { ProgressionChart, type Metric } from "@/components/ProgressionChart";
import { Loading, Ready } from "@/components/State";
import { MAX_COMPARED } from "@/lib/colors";
import { useJson } from "@/lib/data";
import { assignSlots, toggleDriver } from "@/lib/race";
import { biggestMovers, gainedLabel, podiumNames, type SeasonDoc, type SeasonIndex, type SeasonRace } from "@/lib/seasons";

const TABS = [
  { id: "standings", label: "Standings" },
  { id: "progression", label: "Points progression" },
  { id: "races", label: "Races" },
] as const;
type Tab = (typeof TABS)[number]["id"];

function Standings({ doc }: { doc: SeasonDoc }) {
  return (
    <div className="two-col">
      <div>
        <h2>Drivers</h2>
        <div className="table-wrap">
          <table className="narrow">
            <thead><tr><th className="num">Pos</th><th>Driver</th><th>Team</th><th className="num">Wins</th><th className="num">Points</th></tr></thead>
            <tbody>
              {doc.drivers.map((d) => (
                <tr key={d.driver_id}><td className="num">{d.position}</td><td>{d.name}</td><td className="muted">{d.team ?? ""}</td><td className="num">{d.wins}</td><td className="num"><strong>{d.points ?? 0}</strong></td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div>
        <h2>Constructors</h2>
        {doc.constructors.length === 0 ? <p className="muted">No constructors&apos; championship this season.</p> : (
          <div className="table-wrap">
            <table className="narrow">
              <thead><tr><th className="num">Pos</th><th>Team</th><th className="num">Wins</th><th className="num">Points</th></tr></thead>
              <tbody>
                {doc.constructors.map((c) => (
                  <tr key={c.constructor_id}><td className="num">{c.position}</td><td>{c.name}</td><td className="num">{c.wins}</td><td className="num"><strong>{c.points ?? 0}</strong></td></tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function Progression({ doc }: { doc: SeasonDoc }) {
  const series = doc.progression.drivers;
  const order = useMemo(() => series.map((s) => s.code), [series]);
  const byCode = useMemo(() => new Map(series.map((s) => [s.code, s.driver_id])), [series]);
  const [metric, setMetric] = useState<Metric>("points");
  const [slots, setSlots] = useState<(string | null)[]>(() =>
    assignSlots(Array(MAX_COMPARED).fill(null), series.slice(0, MAX_COMPARED).map((s) => s.code), MAX_COMPARED));
  const ids = slots.map((c) => (c ? byCode.get(c) ?? null : null));
  const imputed = series.filter((s) => s.imputed).map((s) => s.code);

  function toggle(code: string) {
    const selected = slots.filter((x): x is string => x !== null);
    setSlots(assignSlots(slots, toggleDriver(selected, code, MAX_COMPARED), MAX_COMPARED));
  }

  return (
    <>
      <div className="filters">
        <div role="group" aria-label="Measure" className="chips">
          {(["points", "position"] as const).map((m) => (
            <button key={m} type="button" className={`chip${m === metric ? " chip-on" : ""}`} aria-pressed={m === metric} onClick={() => setMetric(m)}>
              {m === "points" ? "Points" : "Championship position"}
            </button>
          ))}
        </div>
      </div>
      <DriverPicker order={order} slots={slots} onToggle={toggle} />
      <ProgressionChart rounds={doc.progression.rounds} series={series} slots={ids} metric={metric} />
      {imputed.length > 0 && (
        <p className="muted small">
          Some sprint results in this season have no points in the source data, so they were worked out from the sprint finishing order (8-7-6-5-4-3-2-1).
          Affects: {imputed.join(", ")}.
        </p>
      )}
    </>
  );
}

function RaceCard({ race }: { race: SeasonRace }) {
  const [open, setOpen] = useState(false);
  const { gain, loss } = biggestMovers(race);
  return (
    <li className="race-card">
      <div className="round-title">
        <span className="round-no num">R{String(race.round).padStart(2, "0")}</span>
        <div>
          <h3>{race.name}</h3>
          <p className="muted small">{race.date ?? ""}</p>
        </div>
      </div>
      <p className="podium">{podiumNames(race).map((n, i) => <span key={n}><span className="muted">{i + 1}</span> {n}</span>)}</p>
      <p className="muted small">
        {gain && <>Most places gained: {gain.name} ({gainedLabel(gain.gained)}). </>}
        {loss && <>Most lost: {loss.name} ({gainedLabel(loss.gained)}).</>}
      </p>
      <button type="button" className="chip" aria-expanded={open} onClick={() => setOpen(!open)}>{open ? "Hide results" : "Full results"}</button>
      {open && (
        <div className="table-wrap">
          <table>
            <thead><tr><th className="num">Pos</th><th>Driver</th><th>Team</th><th className="num">Grid</th><th className="num">+/−</th><th className="num">Points</th><th>Status</th></tr></thead>
            <tbody>
              {race.results.map((r) => (
                <tr key={r.driver_id}>
                  <td className="num">{r.position ?? "–"}</td>
                  <td>{r.name}{r.fastest ? " (fastest lap)" : ""}</td>
                  <td className="muted">{r.team ?? ""}</td>
                  <td className="num">{r.grid ? r.grid : r.grid === 0 ? "Pit" : "–"}</td>
                  <td className="num">{gainedLabel(r.gained)}</td>
                  <td className="num">{r.points ?? 0}</td>
                  <td className="muted">{r.status ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </li>
  );
}

function SeasonView({ year }: { year: number }) {
  const load = useJson<SeasonDoc>(`/season-data/${year}.json`);
  const [tab, setTab] = useState<Tab>("standings");
  return (
    <Ready load={load} label={`Loading ${year}`}>
      {(doc) => (
        <>
          <div role="tablist" aria-label="Season view" className="chips">
            {TABS.map((t) => (
              <button key={t.id} role="tab" type="button" aria-selected={t.id === tab} className={`chip${t.id === tab ? " chip-on" : ""}`} onClick={() => setTab(t.id)}>{t.label}</button>
            ))}
          </div>
          {tab === "standings" && <Standings doc={doc} />}
          {tab === "progression" && <Progression doc={doc} />}
          {tab === "races" && <ol className="race-list">{doc.races.map((r) => <RaceCard key={r.round} race={r} />)}</ol>}
        </>
      )}
    </Ready>
  );
}

function Seasons() {
  const params = useSearchParams();
  const router = useRouter();
  const index = useJson<SeasonIndex>("/season-data/index.json");
  return (
    <Ready load={index} label="Loading seasons">
      {({ seasons }) => {
        const years = seasons.map((s) => s.season).sort((a, b) => b - a);
        const asked = Number(params.get("year"));
        const year = years.includes(asked) ? asked : years[0];
        const entry = seasons.find((s) => s.season === year);
        return (
          <>
            <div className="filters">
              <div role="group" aria-label="Season" className="chips">
                {years.map((y) => (
                  <button key={y} type="button" className={`chip${y === year ? " chip-on" : ""}`} aria-pressed={y === year} onClick={() => router.replace(`/seasons?year=${y}`)}>{y}</button>
                ))}
              </div>
            </div>
            {entry?.champion && (
              <p className="muted">
                {year === years[0] ? `Leader after ${entry.rounds} rounds` : `${year} champion`}: <strong>{entry.champion}</strong> ({entry.champion_points} points)
                {entry.constructor_champion ? <>, constructors: <strong>{entry.constructor_champion}</strong></> : null}.
              </p>
            )}
            <SeasonView key={year} year={year} />
          </>
        );
      }}
    </Ready>
  );
}

export default function SeasonsPage() {
  return (
    <>
      <section className="hero hero-small">
        <h1>Seasons</h1>
        <p className="lede">Final standings, how each championship built up round by round, and every race result with its podium and the places gained or lost from the grid.</p>
        <p className="crumb"><Link href="/sessions">Browse sessions</Link></p>
      </section>
      <Suspense fallback={<Loading label="Loading seasons" />}>
        <Seasons />
      </Suspense>
    </>
  );
}
