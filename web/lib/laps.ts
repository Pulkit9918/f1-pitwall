// Laps with sector times and sector colours, as written by scripts/export_laps.py, and the comparisons of two drivers.

export interface LapDriver {
  code: string;
  team: string;
  n: number[];
  t: (number | null)[];
  s1: (number | null)[];
  s2: (number | null)[];
  s3: (number | null)[];
  c: string[]; // three letters per lap: p purple, g green, y yellow, - none
  k: (string | null)[];
  a: (number | null)[];
  w: (string | null)[];
  o: number[];
  i: number[];
  x: number[];
}

export interface LapDoc {
  schema: number;
  session_key: string;
  year: number;
  round: number;
  session_code: string;
  event: string;
  circuit_name: string | null;
  best: Record<string, { t: number; d: string }>;
  drivers: LapDriver[];
}

export interface LapIndex {
  generator: string;
  schema: number;
  sessions: { key: string; year: number; round: number; session_code: string; event: string; drivers: number; laps: number }[];
}

export type SectorColour = "purple" | "green" | "yellow" | "none";

export interface LapRow {
  n: number;
  time: number | null;
  sectors: (number | null)[];
  colours: SectorColour[];
  compound: string | null;
  age: number | null;
  status: string | null;
  clean: boolean;
  pit: boolean;
  deleted: boolean;
}

const COLOUR: Record<string, SectorColour> = { p: "purple", g: "green", y: "yellow" };

export function lapRows(d: LapDriver): LapRow[] {
  return d.n.map((n, i) => ({
    n,
    time: d.t[i],
    sectors: [d.s1[i], d.s2[i], d.s3[i]],
    colours: Array.from(d.c[i] ?? "---", (ch) => COLOUR[ch] ?? "none"),
    compound: d.k[i],
    age: d.a[i],
    status: d.w[i],
    clean: d.o[i] === 1,
    pit: d.i[i] === 1,
    deleted: d.x[i] === 1,
  }));
}

export function median(xs: number[]): number | null {
  if (xs.length === 0) return null;
  const s = [...xs].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

const min = (xs: number[]) => (xs.length ? Math.min(...xs) : null);
const present = (xs: (number | null)[]): number[] => xs.filter((x): x is number => x != null);

export interface Summary {
  laps: number;
  clean: number;
  best: number | null;
  bestSectors: (number | null)[];
  theoretical: number | null; // the three best sectors added up, which no lap necessarily matched
  medianClean: number | null;
  medianCleanSectors: (number | null)[];
  purple: number; // sector times that were the session's best when they were set
}

export function summarise(rows: LapRow[]): Summary {
  const live = rows.filter((r) => !r.deleted);
  const clean = live.filter((r) => r.clean && !r.pit);
  const bestSectors = [0, 1, 2].map((k) => min(present(live.map((r) => r.sectors[k]))));
  return {
    laps: live.length,
    clean: clean.length,
    best: min(present(live.map((r) => r.time))),
    bestSectors,
    theoretical: bestSectors.every((s) => s !== null) ? bestSectors.reduce((a, b) => a! + b!, 0) : null,
    medianClean: median(present(clean.map((r) => r.time))),
    medianCleanSectors: [0, 1, 2].map((k) => median(present(clean.map((r) => r.sectors[k])))),
    purple: live.reduce((n, r) => n + r.colours.filter((c) => c === "purple").length, 0),
  };
}

export interface Pair {
  n: number;
  lap: number;
  sectors: number[]; // first driver minus second, per sector; positive: the first driver was slower
}

// Laps both drivers drove cleanly (no pit lane, no deleted time, all three sectors timed), matched by lap number.
export function pairedLaps(a: LapRow[], b: LapRow[]): Pair[] {
  const ok = (r: LapRow) => r.clean && !r.pit && !r.deleted && r.time != null && r.sectors.every((s) => s != null);
  const bBy = new Map(b.filter(ok).map((r) => [r.n, r]));
  const out: Pair[] = [];
  for (const r of a.filter(ok)) {
    const q = bBy.get(r.n);
    if (q) out.push({ n: r.n, lap: r.time! - q.time!, sectors: r.sectors.map((s, k) => s! - q.sectors[k]!) });
  }
  return out;
}

// Drivers with a timed lap, quickest first.
export function driversByBest(doc: LapDoc): string[] {
  return doc.drivers
    .map((d) => ({ code: d.code, best: summarise(lapRows(d)).best }))
    .filter((d) => d.best !== null)
    .sort((x, y) => x.best! - y.best! || x.code.localeCompare(y.code))
    .map((d) => d.code);
}

// Race-like sessions, where the same lap number is the same stretch of the race for both drivers.
export const isRaceLike = (code: string) => code === "R" || code === "S";
