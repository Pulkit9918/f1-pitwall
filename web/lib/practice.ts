import { median, stintRows } from "./race";
import type { Maybe, SessionDoc } from "./types";

const finite = (v: Maybe<number> | undefined): v is number => typeof v === "number" && Number.isFinite(v);

export interface FastLap {
  driver: string;
  time: number;
  lap: number;
  compound: string | null;
  tyreAge: number | null;
  gap: number; // seconds behind the fastest lap of the session
  laps: number; // timed laps the driver drove
}

// Each driver's quickest timed lap that was not deleted, quickest first.
export function fastestLaps(doc: SessionDoc): FastLap[] {
  const l = doc.laps;
  const best = new Map<string, { time: number; i: number }>();
  const counts = new Map<string, number>();
  for (let i = 0; i < l.driver_code.length; i++) {
    const t = l.lap_time_s[i];
    if (!finite(t) || l.deleted[i] === true) continue;
    const d = l.driver_code[i];
    counts.set(d, (counts.get(d) ?? 0) + 1);
    const cur = best.get(d);
    if (!cur || t < cur.time) best.set(d, { time: t, i });
  }
  const rows = [...best].map(([driver, { time, i }]) => ({
    driver, time, lap: l.lap_number[i], compound: l.compound[i]?.toUpperCase() ?? null, tyreAge: l.tyre_life[i] ?? null, gap: 0, laps: counts.get(driver) ?? 0,
  }));
  rows.sort((a, b) => a.time - b.time || a.driver.localeCompare(b.driver));
  const top = rows[0]?.time ?? 0;
  return rows.map((r) => ({ ...r, gap: r.time - top }));
}

export interface LongRun {
  driver: string;
  compound: string;
  startLap: number;
  endLap: number;
  laps: number;
  cleanLaps: number;
  pace: number; // median clean lap, seconds
  degradation: Maybe<number>; // seconds per lap
  gap: number; // seconds behind the quickest long run on the same compound
}

export const LONG_RUN_MIN_CLEAN = 5;

// Runs with enough clean laps to say something about race pace, grouped by compound and quickest first. Pace is only
// compared within a compound: fuel load and engine mode are not in the data, so a gap between compounds means little.
export function longRuns(doc: SessionDoc, minClean = LONG_RUN_MIN_CLEAN): { compound: string; runs: LongRun[] }[] {
  const byCompound = new Map<string, Omit<LongRun, "gap">[]>();
  for (const s of stintRows(doc)) {
    if (s.cleanLaps < minClean || !finite(s.medianCleanLap)) continue;
    const list = byCompound.get(s.compound) ?? [];
    list.push({ driver: s.driver, compound: s.compound, startLap: s.startLap, endLap: s.endLap, laps: s.laps, cleanLaps: s.cleanLaps, pace: s.medianCleanLap, degradation: s.degradation });
    byCompound.set(s.compound, list);
  }
  const order = ["SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET"];
  return [...byCompound]
    .sort((a, b) => (order.indexOf(a[0]) + 1 || 99) - (order.indexOf(b[0]) + 1 || 99))
    .map(([compound, runs]) => {
      runs.sort((a, b) => a.pace - b.pace || a.driver.localeCompare(b.driver));
      return { compound, runs: runs.map((r) => ({ ...r, gap: r.pace - runs[0].pace })) };
    });
}

// How a driver spent the session: runs, and how many were long.
export function runSummary(doc: SessionDoc, driver: string, minClean = LONG_RUN_MIN_CLEAN): { runs: number; longRuns: number; laps: number } {
  const mine = stintRows(doc).filter((s) => s.driver === driver);
  return { runs: mine.length, longRuns: mine.filter((s) => s.cleanLaps >= minClean).length, laps: mine.reduce((n, s) => n + s.laps, 0) };
}

export { median };
