// Groups a flat list of sessions into years and race weekends, for the session pickers.
import { SESSION_NAMES } from "./format";

export interface WeekendSession {
  key: string;
  year: number;
  round: number;
  session_code: string;
  event: string;
  name?: string | null;
}

export interface WeekendLink {
  key: string;
  code: string;
  label: string;
}

export interface Weekend {
  year: number;
  round: number;
  event: string;
  sessions: WeekendLink[];
}

export interface YearGroup {
  year: number;
  weekends: Weekend[];
}

// The order a weekend runs in, roughly: practice, sprint qualifying, sprint, qualifying, race.
export const SESSION_ORDER = ["FP1", "FP2", "FP3", "SQ", "SS", "S", "Q", "R"];

const rank = (code: string) => {
  const i = SESSION_ORDER.indexOf(code);
  return i === -1 ? SESSION_ORDER.length : i;
};

// Newest year first, rounds in order, sessions in weekend order. `codes` keeps only those session codes.
export function groupWeekends(list: WeekendSession[], codes?: string[]): YearGroup[] {
  const byWeekend = new Map<string, Weekend>();
  for (const s of list) {
    if (codes && !codes.includes(s.session_code)) continue;
    const id = `${s.year}-${s.round}`;
    let w = byWeekend.get(id);
    if (!w) {
      w = { year: s.year, round: s.round, event: s.event, sessions: [] };
      byWeekend.set(id, w);
    }
    w.sessions.push({ key: s.key, code: s.session_code, label: s.name || SESSION_NAMES[s.session_code] || s.session_code });
  }
  const years = new Map<number, Weekend[]>();
  for (const w of byWeekend.values()) {
    w.sessions.sort((a, b) => rank(a.code) - rank(b.code) || a.code.localeCompare(b.code));
    years.set(w.year, [...(years.get(w.year) ?? []), w]);
  }
  return [...years.entries()]
    .sort((a, b) => b[0] - a[0])
    .map(([year, weekends]) => ({ year, weekends: weekends.sort((a, b) => a.round - b.round) }));
}

// The wanted year if there are sessions for it, otherwise the newest year; null when there is nothing to show.
export function pickYear(groups: YearGroup[], wanted: string | null): number | null {
  const y = wanted === null ? NaN : Number(wanted);
  if (groups.some((g) => g.year === y)) return y;
  return groups[0]?.year ?? null;
}
