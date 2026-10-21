import type { LapBand, Maybe, PitStop, Point, SessionDoc, Stint } from "./types";

const finite = (v: Maybe<number> | undefined): v is number => typeof v === "number" && Number.isFinite(v);

export function quantile(sorted: number[], q: number): number {
  if (sorted.length === 0) return NaN;
  const pos = (sorted.length - 1) * q;
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
}

export function median(values: number[]): number {
  return quantile([...values].sort((a, b) => a - b), 0.5);
}

export function maxLap(doc: SessionDoc): number {
  let m = 0;
  for (const n of doc.laps.lap_number) if (n > m) m = n;
  return m;
}

export function stintRows(doc: SessionDoc): Stint[] {
  const s = doc.stints;
  const rows: Stint[] = [];
  for (let i = 0; i < s.driver_code.length; i++) {
    const start = s.start_lap[i];
    const end = s.end_lap[i];
    if (!finite(start) || !finite(end)) continue;
    rows.push({
      driver: s.driver_code[i],
      stint: s.stint[i],
      compound: (s.compound[i] || "UNKNOWN").toUpperCase(),
      startLap: start,
      endLap: end,
      laps: finite(s.laps[i]) ? s.laps[i]! : end - start + 1,
      cleanLaps: s.clean_laps[i] ?? 0,
      medianCleanLap: s.median_clean_lap_s[i],
      degradation: s.degradation_s_per_lap[i],
    });
  }
  return rows;
}

export function pitRows(doc: SessionDoc): PitStop[] {
  const p = doc.pit_stops;
  const rows: PitStop[] = [];
  for (let i = 0; i < p.driver_code.length; i++) {
    const lap = p.in_lap[i];
    if (!finite(lap)) continue;
    rows.push({
      driver: p.driver_code[i],
      lap,
      pitLane: p.pit_lane_time_s[i],
      before: p.compound_before[i],
      after: p.compound_after[i],
      green: p.is_green_stop[i] === true,
      positionBefore: p.position_before[i],
    });
  }
  return rows.sort((a, b) => a.lap - b.lap || a.driver.localeCompare(b.driver));
}

export function driverOrder(doc: SessionDoc): string[] {
  const last = new Map<string, { lap: number; pos: number | null }>();
  const { driver_code, lap_number, position } = doc.laps;
  for (let i = 0; i < driver_code.length; i++) {
    const d = driver_code[i];
    const cur = last.get(d);
    if (!cur || lap_number[i] > cur.lap) last.set(d, { lap: lap_number[i], pos: position[i] });
  }
  const codes = [...last.keys()];
  const hasPositions = codes.some((c) => finite(last.get(c)!.pos));
  if (!hasPositions) return codes.sort();
  return codes.sort((a, b) => {
    const x = last.get(a)!;
    const y = last.get(b)!;
    if (x.lap !== y.lap) return y.lap - x.lap;
    return (x.pos ?? 99) - (y.pos ?? 99) || a.localeCompare(b);
  });
}

interface Bound {
  lap: number;
  start: number;
  end: number;
}

export function lapBounds(doc: SessionDoc): Bound[] {
  const ends = new Map<number, number[]>();
  const starts = new Map<number, number[]>();
  const { lap_number, time_s, lap_start_time_s } = doc.laps;
  for (let i = 0; i < lap_number.length; i++) {
    const n = lap_number[i];
    if (finite(time_s[i])) (ends.get(n) ?? ends.set(n, []).get(n)!).push(time_s[i]!);
    if (finite(lap_start_time_s[i])) (starts.get(n) ?? starts.set(n, []).get(n)!).push(lap_start_time_s[i]!);
  }
  const out: Bound[] = [];
  let prevEnd: number | null = null;
  for (const lap of [...ends.keys()].sort((a, b) => a - b)) {
    const end = median(ends.get(lap)!);
    const start = prevEnd ?? (starts.has(lap) ? median(starts.get(lap)!) : NaN);
    if (Number.isFinite(start) && end > start) out.push({ lap, start, end });
    prevEnd = end;
  }
  return out;
}

export function timeToLap(t: number, bounds: Bound[]): number | null {
  if (bounds.length === 0) return null;
  if (t <= bounds[0].start) return bounds[0].lap - 1;
  for (const b of bounds) {
    if (t < b.end) return b.lap - 1 + Math.max(0, (t - b.start) / (b.end - b.start));
  }
  return bounds[bounds.length - 1].lap;
}

export function periodBands(doc: SessionDoc): LapBand[] {
  const bounds = lapBounds(doc);
  if (bounds.length === 0) return [];
  const sessionEnd = bounds[bounds.length - 1].end;
  const bands: LapBand[] = [];
  for (const p of doc.race_control_periods) {
    if (!p.has_session_clock || !finite(p.start_s)) continue;
    const x0 = timeToLap(p.start_s, bounds);
    const x1 = timeToLap(finite(p.end_s) ? p.end_s : sessionEnd, bounds);
    if (x0 == null || x1 == null || x1 <= x0) continue;
    bands.push({ kind: p.kind, x0, x1 });
  }
  return bands;
}

export function cleanSeries(doc: SessionDoc, driver: string): Point[] {
  const { driver_code, lap_number, lap_time_s, is_clean_lap } = doc.laps;
  const out: Point[] = [];
  for (let i = 0; i < driver_code.length; i++) {
    if (driver_code[i] === driver && is_clean_lap[i] === true && finite(lap_time_s[i])) {
      out.push({ lap: lap_number[i], value: lap_time_s[i]! });
    }
  }
  return out.sort((a, b) => a.lap - b.lap);
}

export function positionSeries(doc: SessionDoc, driver: string): Point[] {
  const { driver_code, lap_number, position } = doc.laps;
  const out: Point[] = [];
  for (let i = 0; i < driver_code.length; i++) {
    if (driver_code[i] === driver && finite(position[i])) out.push({ lap: lap_number[i], value: position[i]! });
  }
  return out.sort((a, b) => a.lap - b.lap);
}

export function hasPositions(doc: SessionDoc): boolean {
  return doc.laps.position.some(finite);
}

export function lapDomain(series: Point[][]): [number, number] | null {
  const all = series.flatMap((s) => s.map((p) => p.value)).sort((a, b) => a - b);
  if (all.length === 0) return null;
  const lo = all[0];
  const hi = quantile(all, 0.98);
  const pad = Math.max((hi - lo) * 0.06, 0.2);
  return [lo - pad, hi + pad];
}

export function toggleDriver(selected: string[], code: string, max: number): string[] {
  if (selected.includes(code)) return selected.filter((c) => c !== code);
  return selected.length >= max ? selected : [...selected, code];
}

export function slotOf(slots: (string | null)[], code: string): number {
  return slots.indexOf(code);
}

export function assignSlots(slots: (string | null)[], selected: string[], max: number): (string | null)[] {
  const next = Array.from({ length: max }, (_, i) => (selected.includes(slots[i] ?? "") ? slots[i] : null));
  for (const code of selected) {
    if (!next.includes(code)) {
      const free = next.indexOf(null);
      if (free >= 0) next[free] = code;
    }
  }
  return next;
}
