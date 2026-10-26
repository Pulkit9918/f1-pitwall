// Lap telemetry against distance, as written by scripts/export_traces.py. Every lap of a session is sampled at the
// same P distances from the line to the line, so two laps can be compared point by point.

export interface TraceLapMeta {
  n: number;
  t: number | null;
  c?: string;
  a?: number;
  s?: string;
  k?: 0 | 1; // 1: has a trace and its speed channel agrees with the positions; 0: has a trace, time only
  r?: string; // why a lap has no trace
}

export interface TraceSession {
  schema: number;
  session_key: string;
  year: number;
  round: number;
  session_code: string;
  event: string;
  circuit_name: string | null;
  country: string | null;
  layout: string | null;
  ref_length_m: number;
  points: number;
  dist: number[];
  drivers: { code: string; team: string; laps: TraceLapMeta[] }[];
}

export interface TraceIndex {
  generator: string;
  schema: number;
  sessions: { key: string; year: number; round: number; session_code: string; event: string; circuit_name: string | null; drivers: number; laps: number }[];
}

export interface EncodedLap {
  dt: number[];
  v?: number[];
  th?: number[];
  g?: string;
  d?: string;
  b?: string;
}

export interface TraceDriverFile {
  schema: number;
  session_key: string;
  driver: string;
  points: number;
  laps: Record<string, EncodedLap>;
}

export interface Lap {
  time: number[]; // seconds since the line, at each point
  speed: number[] | null;
  throttle: number[] | null;
  brake: number[] | null; // 0 or 1
  gear: number[] | null;
  drs: number[] | null; // 1 when the flap is open
}

// DRS codes follow the timing feed: 10, 12 and 14 mean open, the lower codes closed or not yet allowed.
export const DRS_OPEN_FROM = 10;

export function decodeLap(enc: EncodedLap): Lap {
  const time = [0];
  for (const d of enc.dt) time.push(time[time.length - 1] + d / 100);
  const has = enc.v !== undefined && enc.g !== undefined && enc.d !== undefined && enc.b !== undefined && enc.th !== undefined;
  return {
    time,
    speed: has ? enc.v! : null,
    throttle: has ? enc.th! : null,
    brake: has ? Array.from(enc.b!, (c) => (c === "1" ? 1 : 0)) : null,
    gear: has ? Array.from(enc.g!, (c) => c.charCodeAt(0) - 48) : null,
    drs: has ? Array.from(enc.d!, (c) => (parseInt(c, 16) >= DRS_OPEN_FROM ? 1 : 0)) : null,
  };
}

// Seconds the lap is behind the reference at each point (positive: slower so far). The reference is 0 throughout.
export function deltaTo(ref: Lap, lap: Lap): number[] {
  return lap.time.map((t, i) => t - ref.time[i]);
}

// The traced lap with the shortest lap time, preferring laps whose speed channel can be trusted.
export function fastestLap(laps: TraceLapMeta[]): TraceLapMeta | null {
  const traced = laps.filter((l) => l.k !== undefined && l.t != null);
  const pool = traced.some((l) => l.k === 1) ? traced.filter((l) => l.k === 1) : traced;
  return pool.reduce<TraceLapMeta | null>((best, l) => (best === null || l.t! < best.t! ? l : best), null);
}

export function tracedLaps(laps: TraceLapMeta[]): TraceLapMeta[] {
  return laps.filter((l) => l.k !== undefined);
}

// Drivers with a traced lap, quickest first.
export function driversByPace(drivers: TraceSession["drivers"]): string[] {
  return drivers
    .map((d) => ({ code: d.code, best: fastestLap(d.laps)?.t ?? null }))
    .filter((d) => d.best !== null)
    .sort((a, b) => a.best! - b.best! || a.code.localeCompare(b.code))
    .map((d) => d.code);
}

export const REASONS: Record<string, string> = {
  standing_start: "starts from standstill (grid or garage)",
  pit_lap: "pit lap",
  no_telemetry: "no telemetry",
  late_start: "telemetry starts late",
  early_end: "telemetry ends early",
  data_gap: "gap in the position feed",
  layout_unreliable: "track length not established",
  length_off: "distance does not match the track",
};

export function reasonText(r: string | undefined): string {
  return (r && REASONS[r]) || r || "no trace";
}

// A chosen lap. The colour belongs to the slot and stays with the lap while it is chosen.
export interface Pick {
  driver: string;
  lap: number;
}

export const MAX_LAPS = 8;

export const pickKey = (p: Pick) => `${p.driver}:${p.lap}`;

export function pickColors(picks: Pick[], slots: Record<string, number>, count = MAX_LAPS): Record<string, number> {
  const out: Record<string, number> = {};
  const used = new Set<number>();
  for (const p of picks) {
    const s = slots[pickKey(p)];
    if (s !== undefined && s < count && !used.has(s)) {
      out[pickKey(p)] = s;
      used.add(s);
    }
  }
  for (const p of picks) {
    if (out[pickKey(p)] !== undefined) continue;
    let s = 0;
    while (used.has(s)) s++;
    out[pickKey(p)] = s;
    used.add(s);
  }
  return out;
}

export function addPick(picks: Pick[], p: Pick, max = MAX_LAPS): Pick[] {
  if (picks.some((q) => pickKey(q) === pickKey(p)) || picks.length >= max) return picks;
  return [...picks, p];
}

export function removePick(picks: Pick[], p: Pick): Pick[] {
  return picks.filter((q) => pickKey(q) !== pickKey(p));
}

// The index of the grid point nearest to a distance.
export function nearestIndex(dist: number[], d: number): number {
  let lo = 0;
  let hi = dist.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (dist[mid] <= d) lo = mid;
    else hi = mid;
  }
  return Math.abs(dist[lo] - d) <= Math.abs(dist[hi] - d) ? lo : hi;
}

// Moves end labels apart so that none is closer than `gap` to the next, keeping their order, then back inside [lo, hi].
export function spreadLabels(ys: number[], gap: number, lo: number, hi: number): number[] {
  const order = ys.map((y, i) => i).sort((a, b) => ys[a] - ys[b]);
  const out = ys.slice();
  let prev = lo - gap;
  for (const i of order) {
    out[i] = Math.max(ys[i], prev + gap);
    prev = out[i];
  }
  let next = hi + gap;
  for (const i of order.slice().reverse()) {
    out[i] = Math.min(out[i], next - gap);
    next = out[i];
  }
  return out;
}

export function lapLabel(p: Pick): string {
  return `${p.driver} lap ${p.lap}`;
}

// The same laps from one set of drivers' files, ready to draw.
export interface DrawnLap {
  pick: Pick;
  slot: number;
  meta: TraceLapMeta | undefined;
  lap: Lap;
}

export function drawLaps(
  picks: Pick[],
  slots: Record<string, number>,
  session: TraceSession,
  files: Record<string, TraceDriverFile | undefined>,
): DrawnLap[] {
  const out: DrawnLap[] = [];
  for (const p of picks) {
    const enc = files[p.driver]?.laps[String(p.lap)];
    if (!enc || enc.dt.length !== session.points - 1) continue;
    out.push({
      pick: p,
      slot: slots[pickKey(p)] ?? 0,
      meta: session.drivers.find((d) => d.code === p.driver)?.laps.find((l) => l.n === p.lap),
      lap: decodeLap(enc),
    });
  }
  return out;
}

// What the track status codes of a lap mean for how it was driven; null for a clear lap.
export function statusNote(s: string | undefined): string | null {
  if (!s) return null;
  if (s.includes("5")) return "red flag";
  if (s.includes("4")) return "safety car";
  if (/[67]/.test(s)) return "virtual safety car";
  if (s.includes("2")) return "yellow flag";
  return null;
}

export function lapOption(l: TraceLapMeta, fmtLap: (s: number | null) => string): string {
  const parts = [`Lap ${l.n}`, fmtLap(l.t ?? null)];
  if (l.c) parts.push(l.a != null ? `${l.c.toLowerCase()}, ${l.a} laps old` : l.c.toLowerCase());
  const note = statusNote(l.s);
  if (note) parts.push(note);
  if (l.k === undefined) parts.push(`no trace: ${reasonText(l.r)}`);
  else if (l.k === 0) parts.push("time only");
  return parts.join(" · ");
}
