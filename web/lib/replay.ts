// Everything the replay page works out from a replay file and the session's lap table. Plain functions, no React.
import type { Maybe, SessionDoc } from "./types";

// ---- the file written by scripts/export_replay.py ----

export interface ReplayDriver {
  num: number;
  a: number; // first frame with data
  b: number; // last frame with data
  p0: number; // progress at frame 0, in 1e-4 laps
  dp: number[]; // change in progress from each frame to the next, in 1e-4 laps
  spd?: number[];
  gear?: number[];
  thr?: number[];
  brk?: number[];
  drs?: number[];
}

export interface WeatherSeries {
  t: Maybe<number>[];
  air: Maybe<number>[];
  track: Maybe<number>[];
  humidity: Maybe<number>[];
  rain: Maybe<number>[];
  wind: Maybe<number>[];
  wind_dir: Maybe<number>[];
}

// [session time, category, flag, lap, text, driver code]
export type ReplayMessage = [number, string, string, Maybe<number>, string, Maybe<string>];

export interface ReplayFile {
  schema: number;
  key: string;
  kind: "race" | "quali";
  t0: number;
  step: number;
  n: number;
  track: { w: number; h: number; pts: [number, number][] };
  drivers: Record<string, ReplayDriver>;
  weather: Maybe<WeatherSeries>;
  messages: ReplayMessage[];
  track_status: [number, string, string][];
  teams?: Record<string, [Maybe<string>, Maybe<string>]>; // driver code -> [team name, "#RRGGBB"]
}

export interface TeamInfo {
  name: Maybe<string>;
  color: Maybe<string>;
  second: boolean; // the team's second car (higher car number), drawn with a dark centre so teammates differ without colour
}

export interface Replay {
  file: ReplayFile;
  codes: string[];
  t0: number;
  step: number;
  end: number;
  cum: Record<string, Float64Array>; // progress in laps, one value per frame
  mono: Record<string, Float64Array>; // the same, never decreasing, for working out gaps
  teams: Record<string, TeamInfo>;
}

export function decodeReplay(file: ReplayFile): Replay {
  const cum: Record<string, Float64Array> = {};
  const mono: Record<string, Float64Array> = {};
  for (const [code, d] of Object.entries(file.drivers)) {
    const c = new Float64Array(file.n);
    const m = new Float64Array(file.n);
    let v = d.p0;
    c[0] = v / 1e4;
    m[0] = c[0];
    for (let i = 1; i < file.n; i++) {
      v += d.dp[i - 1] ?? 0;
      c[i] = v / 1e4;
      m[i] = Math.max(m[i - 1], c[i]);
    }
    cum[code] = c;
    mono[code] = m;
  }
  const teams: Record<string, TeamInfo> = {};
  const byTeam = new Map<string, string[]>();
  for (const [code, [name]] of Object.entries(file.teams ?? {})) {
    if (!file.drivers[code] || !name) continue;
    byTeam.set(name, [...(byTeam.get(name) ?? []), code]);
  }
  for (const [code, [name, color]] of Object.entries(file.teams ?? {})) {
    if (!file.drivers[code]) continue;
    const mates = (name ? byTeam.get(name) : null) ?? [code];
    mates.sort((a, b) => file.drivers[a].num - file.drivers[b].num);
    teams[code] = { name: name ?? null, color: color ?? null, second: mates.indexOf(code) > 0 };
  }
  return { file, codes: Object.keys(file.drivers), t0: file.t0, step: file.step, end: file.t0 + (file.n - 1) * file.step, cum, mono, teams };
}

export const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

// The frame at or before time t and how far (0 to 1) t is towards the next one.
export function frame(r: Replay, t: number): { i: number; f: number } {
  if (r.file.n < 2) return { i: 0, f: 0 };
  const x = clamp((t - r.t0) / r.step, 0, r.file.n - 1);
  const i = Math.min(Math.floor(x), r.file.n - 2);
  return { i, f: x - i };
}

export function cumAt(r: Replay, code: string, t: number): number {
  const arr = r.cum[code];
  if (!arr) return NaN;
  const { i, f } = frame(r, t);
  return arr[i] + ((arr[i + 1] ?? arr[i]) - arr[i]) * f;
}

// Does the car have position data at time t?
export function hasData(r: Replay, code: string, t: number): boolean {
  const d = r.file.drivers[code];
  if (!d) return false;
  const x = (t - r.t0) / r.step;
  return x >= d.a - 1e-9 && x <= d.b + 1e-9;
}

// A point on the closed outline at a fraction (0 to 1, wrapping) of a lap.
export function trackPoint(pts: [number, number][], frac: number): [number, number] {
  const n = pts.length;
  const u = (((frac % 1) + 1) % 1) * n;
  const i = Math.floor(u);
  const f = u - i;
  const a = pts[i % n];
  const b = pts[(i + 1) % n];
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f];
}

// The time at which a car first reached `c` laps of progress, or null if it never did.
export function timeAtCum(r: Replay, code: string, c: number): number | null {
  const arr = r.mono[code];
  if (!arr || c > arr[arr.length - 1]) return null;
  if (c <= arr[0]) return r.t0;
  let lo = 0;
  let hi = arr.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (arr[mid] >= c) hi = mid;
    else lo = mid + 1;
  }
  const k = lo;
  const span = arr[k] - arr[k - 1];
  return r.t0 + (k - 1 + (span > 0 ? (c - arr[k - 1]) / span : 0)) * r.step;
}

export function channelAt(r: Replay, code: string, t: number) {
  const d = r.file.drivers[code];
  if (!d || !d.spd || !hasData(r, code, t)) return null;
  const { i, f } = frame(r, t);
  const k = f >= 0.5 ? Math.min(i + 1, r.file.n - 1) : i;
  return {
    speed: d.spd[k],
    gear: d.gear?.[k] ?? 0,
    throttle: d.thr?.[k] ?? 0,
    brake: (d.brk?.[k] ?? 0) > 0,
    drs: d.drs?.[k] ?? 0,
  };
}

// FastF1 reports DRS as a code: 0 and 1 off, 8 eligible, 10, 12 and 14 open. That meaning is taken from its
// documentation and has not been checked against this data.
export const drsOpen = (code: number) => code === 10 || code === 12 || code === 14;

// ---- laps ----

export interface LapRec {
  lap: number;
  start: Maybe<number>;
  end: Maybe<number>;
  time: Maybe<number>;
  s1: Maybe<number>;
  s2: Maybe<number>;
  s3: Maybe<number>;
  compound: Maybe<string>;
  tyreLife: Maybe<number>;
  pitIn: Maybe<number>;
  pitOut: Maybe<number>;
  deleted: boolean;
}

export type LapIndex = Map<string, LapRec[]>;

const fin = (v: Maybe<number> | undefined): v is number => typeof v === "number" && Number.isFinite(v);

export const completed = (l: LapRec) => fin(l.end) && fin(l.time);

export function buildLapIndex(doc: SessionDoc): LapIndex {
  const c = doc.laps;
  const idx: LapIndex = new Map();
  for (let i = 0; i < c.driver_code.length; i++) {
    const start = c.lap_start_time_s[i];
    const time = c.lap_time_s[i];
    let end = c.time_s[i];
    if (!fin(end) && fin(start) && fin(time)) end = start + time;
    const rec: LapRec = {
      lap: c.lap_number[i],
      start: fin(start) ? start : null,
      end: fin(end) ? end : null,
      time: fin(time) ? time : null,
      s1: c.sector1_s[i] ?? null,
      s2: c.sector2_s[i] ?? null,
      s3: c.sector3_s[i] ?? null,
      compound: c.compound[i],
      tyreLife: c.tyre_life[i],
      pitIn: c.pit_in_time_s[i],
      pitOut: c.pit_out_time_s[i],
      deleted: c.deleted[i] === true,
    };
    const list = idx.get(c.driver_code[i]);
    if (list) list.push(rec);
    else idx.set(c.driver_code[i], [rec]);
  }
  for (const list of idx.values()) list.sort((a, b) => a.lap - b.lap);
  return idx;
}

// When the leader finished each lap: index n - 1 is the end of lap n. Used for "Lap 37/52" and the timeline ticks.
export function lapEnds(idx: LapIndex): number[] {
  const best: number[] = [];
  for (const list of idx.values()) {
    for (const l of list) {
      if (!fin(l.end)) continue;
      if (best[l.lap - 1] === undefined || l.end < best[l.lap - 1]) best[l.lap - 1] = l.end;
    }
  }
  return best;
}

export function raceStart(idx: LapIndex, fallback: number): number {
  let s = Infinity;
  for (const list of idx.values()) if (list[0] && fin(list[0].start) && list[0].start < s) s = list[0].start;
  return Number.isFinite(s) ? s : fallback;
}

// The lap the leader is on at time t (1 to total).
export function leaderLap(ends: number[], t: number, total: number): number {
  let n = 0;
  for (const e of ends) {
    if (e !== undefined && e <= t) n++;
    else break;
  }
  return clamp(n + 1, 1, Math.max(1, total));
}

// ---- formatting ----

export function fmtClock(t: number): string {
  const sign = t < 0 ? "-" : "";
  const s = Math.floor(Math.abs(t));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return `${sign}${h > 0 ? `${h}:` : ""}${String(m).padStart(h > 0 ? 2 : 1, "0")}:${String(sec).padStart(2, "0")}`;
}

export function fmtGap(s: number | null | undefined): string {
  return s == null || !Number.isFinite(s) ? "" : `+${s.toFixed(s < 100 ? 3 : 1)}`;
}

// ---- the leaderboard ----

export type CarState = "run" | "pit" | "out" | "fin";

export interface TyreNow {
  compound: Maybe<string>;
  life: Maybe<number>;
  stops: number;
}

export interface BoardRow {
  code: string;
  pos: number;
  state: CarState;
  tyre: TyreNow;
  gapLeader: string; // "Leader", "+12.345", "+1 LAP" or ""
  interval: string;
  progress: number; // laps (race) or best lap time (quali)
  best: Maybe<number>; // quali: best lap so far
}

interface DriverFacts {
  code: string;
  recs: LapRec[];
  cap: number;
  lastEnd: Maybe<number>;
  retired: boolean;
  lastStart: Maybe<number>;
  medianLap: number;
}

export function driverFacts(idx: LapIndex): Map<string, DriverFacts> {
  const out = new Map<string, DriverFacts>();
  for (const [code, recs] of idx) {
    const done = recs.filter(completed);
    const last = recs[recs.length - 1];
    const times = done.map((l) => l.time!).sort((a, b) => a - b);
    out.set(code, {
      code,
      recs,
      cap: last ? last.lap : 0,
      lastEnd: done.length ? done[done.length - 1].end : null,
      retired: !!last && !completed(last),
      lastStart: last ? last.start : null,
      medianLap: times.length ? times[Math.floor(times.length / 2)] : 90,
    });
  }
  return out;
}

export function tyreAt(recs: LapRec[], t: number): TyreNow {
  if (recs.length === 0) return { compound: null, life: null, stops: 0 };
  let cur = recs[0];
  for (const l of recs) {
    if (fin(l.start) && l.start <= t) cur = l;
    else if (!fin(l.start) && fin(l.end) && l.end > t) {
      cur = l;
      break;
    }
  }
  const stops = recs.filter((l) => fin(l.pitIn) && l.pitIn <= t).length;
  return { compound: cur.compound, life: cur.tyreLife, stops };
}

// True from pit entry on one lap to pit exit on the next.
export function inPit(recs: LapRec[], t: number): boolean {
  for (let i = 0; i < recs.length; i++) {
    const pin = recs[i].pitIn;
    if (!fin(pin) || pin > t) continue;
    const next = recs[i + 1];
    const pout = next && fin(next.pitOut) ? next.pitOut : pin + 30;
    if (t <= pout) return true;
  }
  return false;
}

function lapsDown(diff: number): string {
  const k = Math.floor(diff + 1e-9);
  return `+${k} ${k === 1 ? "LAP" : "LAPS"}`;
}

// A car counts as retired if its last lap never finished, or if it stopped three or more laps short of the winner's
// distance. The second rule is a guess for when the lap table has no unfinished last lap; it also catches a car that
// finished three or more laps down.
export interface RaceOpts {
  total: number; // laps the winner completed
  start: number; // session time of the start (gaps are blank before it)
}

export function raceBoard(r: Replay, facts: Map<string, DriverFacts>, t: number, opts: RaceOpts): BoardRow[] {
  const isOut = (f: DriverFacts) => f.retired || f.cap <= opts.total - 3;
  const rows = [...facts.values()]
    .filter((f) => r.file.drivers[f.code])
    .map((f) => {
      const done = fin(f.lastEnd) && t >= f.lastEnd && !isOut(f);
      const c = done ? f.cap : Math.min(cumAt(r, f.code, t), f.cap);
      return { f, c: Number.isFinite(c) ? c : 0, done, tie: done ? f.lastEnd! : t };
    })
    .sort((x, y) => y.c - x.c || x.tie - y.tie);
  const leader = rows[0];
  return rows.map((row, i): BoardRow => {
    const { f, c, done } = row;
    const retiredNow = f.retired
      ? fin(f.lastStart) && t >= f.lastStart + 0.5 * f.medianLap
      : f.cap <= opts.total - 3 && fin(f.lastEnd) && t >= f.lastEnd + 0.75 * f.medianLap;
    const state: CarState = retiredNow ? "out" : inPit(f.recs, t) ? "pit" : done ? "fin" : "run";
    const gapTo = (ahead: (typeof rows)[number]): string => {
      if (t < opts.start) return "";
      const diff = ahead.c - c;
      if (diff >= 1) return lapsDown(diff);
      const reached = timeAtCum(r, ahead.f.code, c);
      if (reached == null) return "";
      const now = done ? f.lastEnd! : t;
      return fmtGap(Math.max(0, now - reached));
    };
    return {
      code: f.code,
      pos: i + 1,
      state,
      tyre: tyreAt(f.recs, t),
      gapLeader: i === 0 ? (t < opts.start ? "" : "Leader") : gapTo(leader),
      interval: i === 0 ? "" : gapTo(rows[i - 1]),
      progress: c,
      best: null,
    };
  });
}

// Qualifying: order by best lap so far.
export function qualiBoard(facts: Map<string, DriverFacts>, t: number): BoardRow[] {
  const rows = [...facts.values()].map((f) => {
    const laps = f.recs.filter((l) => completed(l) && !l.deleted && l.end! <= t);
    const best = laps.length ? Math.min(...laps.map((l) => l.time!)) : null;
    return { f, best };
  });
  rows.sort((a, b) => (a.best ?? Infinity) - (b.best ?? Infinity) || a.f.code.localeCompare(b.f.code));
  const top = rows[0]?.best ?? null;
  return rows.map((row, i): BoardRow => ({
    code: row.f.code,
    pos: i + 1,
    state: inPit(row.f.recs, t) ? "pit" : "run",
    tyre: tyreAt(row.f.recs, t),
    gapLeader: row.best == null ? "" : i === 0 ? "Leader" : `+${(row.best - top!).toFixed(3)}`,
    interval: "",
    progress: row.best ?? Infinity,
    best: row.best,
  }));
}

// ---- the timing table ----

export interface Cell {
  v: Maybe<number>;
  purple: boolean; // the best anyone has done so far
  green: boolean; // the driver's own best so far
}

export interface TimingRow {
  code: string;
  laps: number;
  last: Cell;
  best: Cell;
  sectors: [Cell, Cell, Cell];
}

const EPS = 1e-6;

export function timingRows(idx: LapIndex, order: string[], t: number): TimingRow[] {
  const done = new Map<string, LapRec[]>();
  const overall = { lap: Infinity, s: [Infinity, Infinity, Infinity] };
  const own = new Map<string, { lap: number; s: number[] }>();
  for (const [code, recs] of idx) {
    const list = recs.filter((l) => completed(l) && l.end! <= t);
    done.set(code, list);
    const mine = { lap: Infinity, s: [Infinity, Infinity, Infinity] };
    for (const l of list) {
      if (l.deleted) continue;
      if (l.time! < mine.lap) mine.lap = l.time!;
      [l.s1, l.s2, l.s3].forEach((v, k) => {
        if (fin(v) && v < mine.s[k]) mine.s[k] = v;
      });
    }
    own.set(code, mine);
    overall.lap = Math.min(overall.lap, mine.lap);
    mine.s.forEach((v, k) => (overall.s[k] = Math.min(overall.s[k], v)));
  }
  const cell = (v: Maybe<number>, best: number, mineBest: number): Cell => ({
    v,
    purple: fin(v) && Math.abs(v - best) < EPS,
    green: fin(v) && Math.abs(v - mineBest) < EPS && Math.abs(v - best) >= EPS,
  });
  return order.filter((c) => idx.has(c)).map((code) => {
    const list = done.get(code)!;
    const last = list[list.length - 1];
    const mine = own.get(code)!;
    const usable = last && !last.deleted;
    return {
      code,
      laps: list.length,
      last: usable ? cell(last.time, overall.lap, mine.lap) : { v: last?.time ?? null, purple: false, green: false },
      best: { v: Number.isFinite(mine.lap) ? mine.lap : null, purple: Number.isFinite(mine.lap) && Math.abs(mine.lap - overall.lap) < EPS, green: false },
      sectors: [last?.s1 ?? null, last?.s2 ?? null, last?.s3 ?? null].map((v, k) =>
        usable ? cell(v, overall.s[k], mine.s[k]) : { v, purple: false, green: false },
      ) as [Cell, Cell, Cell],
    };
  });
}

// ---- weather, messages, track status, timeline bands ----

export function weatherAt(w: Maybe<WeatherSeries>, t: number) {
  if (!w || w.t.length === 0) return null;
  let k = 0;
  for (let i = 0; i < w.t.length; i++) {
    const wt = w.t[i];
    if (wt != null && wt <= t) k = i;
    else if (wt != null) break;
  }
  return { air: w.air[k], track: w.track[k], humidity: w.humidity[k], rain: w.rain[k] === 1, wind: w.wind[k], windDir: w.wind_dir[k] };
}

// The newest messages first, up to `limit`.
export function messagesUpTo(file: ReplayFile, t: number, limit = 40): ReplayMessage[] {
  const out: ReplayMessage[] = [];
  for (const m of file.messages) {
    if (m[0] <= t) out.push(m);
    else break;
  }
  return out.slice(-limit).reverse();
}

export function statusAt(file: ReplayFile, t: number): { code: string; label: string } | null {
  let cur: [number, string, string] | null = null;
  for (const s of file.track_status) {
    if (s[0] <= t) cur = s;
    else break;
  }
  return cur ? { code: cur[1], label: cur[2] || cur[1] } : null;
}

export type BandKind = "YELLOW" | "SC" | "VSC" | "RED";
export interface TimeBand {
  kind: BandKind;
  t0: number;
  t1: number;
}

// Safety car, VSC and red flag periods come from the gold table (already checked in this project); yellow flags
// from the track-status feed (code "2", which is an assumption about the feed).
export function timeBands(r: Replay, doc: Maybe<SessionDoc>): TimeBand[] {
  const out: TimeBand[] = [];
  const file = r.file;
  for (let i = 0; i < file.track_status.length; i++) {
    if (file.track_status[i][1] !== "2") continue;
    const next = file.track_status[i + 1];
    out.push({ kind: "YELLOW", t0: file.track_status[i][0], t1: next ? next[0] : r.end });
  }
  for (const p of doc?.race_control_periods ?? []) {
    if (p.start_s == null) continue;
    out.push({ kind: p.kind, t0: p.start_s, t1: p.end_s ?? r.end });
  }
  return out.filter((b) => b.t1 > b.t0).sort((a, b) => a.t0 - b.t0);
}

// ---- gap to a chosen driver, and laps done ----

// For every row, the time to the chosen driver: "+" when the car is behind them, "-" when it is ahead. Same method as the
// gaps on the board: the time since the car in front was at the point the other car has now reached. A lap or more apart
// is shown in laps. Blank before the start, or when the data does not reach.
export function gapsToDriver(r: Replay, rows: BoardRow[], t: number, selected: string, start: number): Map<string, string> {
  const out = new Map<string, string>();
  const sel = rows.find((x) => x.code === selected);
  if (!sel) return out;
  for (const row of rows) {
    if (row.code === selected) {
      out.set(row.code, "Selected");
      continue;
    }
    if (t < start) {
      out.set(row.code, "");
      continue;
    }
    const diff = sel.progress - row.progress; // positive: this car is behind the chosen driver
    const sign = diff >= 0 ? "+" : "-";
    if (Math.abs(diff) >= 1) {
      const k = Math.floor(Math.abs(diff) + 1e-9);
      out.set(row.code, `${sign}${k} ${k === 1 ? "LAP" : "LAPS"}`);
      continue;
    }
    const reached = diff >= 0 ? timeAtCum(r, selected, row.progress) : timeAtCum(r, row.code, sel.progress);
    out.set(row.code, reached == null ? "" : `${sign}${Math.max(0, t - reached).toFixed(3)}`);
  }
  return out;
}

// The number of the last lap a driver has finished by time t, 0 before the first.
export function lapsDoneAt(recs: LapRec[], t: number): number {
  let n = 0;
  for (const l of recs) if (fin(l.end) && l.end <= t && l.lap > n) n = l.lap;
  return n;
}

// The session time at which lap n starts for the leader: the end of lap n - 1, or the race start for lap 1.
export function lapStartTime(ends: number[], n: number, start: number): number | null {
  if (n <= 1) return start;
  const e = ends[n - 2];
  return e === undefined ? null : e;
}

// One row per lap, one column per selected driver, up to the time shown. Purple is the best lap of the session so far
// among all drivers, green the driver's own best so far; laps deleted by the stewards are struck out and not counted.
export function lapHistory(idx: LapIndex, codes: string[], t: number) {
  const all: { code: string; rec: LapRec }[] = [];
  for (const [code, recs] of idx) for (const rec of recs) if (completed(rec) && !rec.deleted && rec.end! <= t) all.push({ code, rec });
  const rows = new Map<number, Map<string, LapRec>>();
  for (const code of codes) {
    for (const rec of idx.get(code) ?? []) {
      if (!completed(rec) || rec.end! > t) continue;
      const row = rows.get(rec.lap) ?? new Map<string, LapRec>();
      row.set(code, rec);
      rows.set(rec.lap, row);
    }
  }
  const laps = [...rows.keys()].sort((a, b) => b - a); // newest first
  const bestOf = (code: string) => Math.min(...all.filter((x) => x.code === code).map((x) => x.rec.time!), Infinity);
  const sessionBest = Math.min(...all.map((x) => x.rec.time!), Infinity);
  return { laps, rows, sessionBest, own: new Map(codes.map((c) => [c, bestOf(c)])) };
}

