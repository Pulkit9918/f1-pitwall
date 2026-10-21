// Types and pure helpers for the per-race analysis (data from scripts/export_analysis.py).
import type { Point } from "./types";

export type Regime = "green" | "sc" | "vsc" | "red" | "unknown";

export interface DriverAnalysis {
  pos: (number | null)[];
  leader: (number | null)[];
  interval: (number | null)[];
  loss: (number | null)[];
  pred: (number | null)[];
  fast: (number | null)[];
  slow: (number | null)[];
  margin: (number | null)[];
  regime: string; 
}
export interface Battle {
  kind: "undercut" | "overcut";
  attacker: string;
  defender: string;
  first_by: string;
  first_lap: number;
  second_lap: number;
  gap_before_s: number | null;
  attacker_ahead: boolean;
  margin_after_s: number | null;
  neutralised: boolean;
}
export interface RatioRow { stops: number; median_loss_s: number | null; p25_loss_s: number | null; p75_loss_s: number | null; ratio: number | null; reliable: boolean }
export interface AnalysisDoc {
  schema: number;
  session_key: string;
  laps: number;
  drivers: string[];
  series: Record<string, DriverAnalysis>;
  stops: { driver: string; lap: number }[];
  battles: Battle[];
  loss_ratio: Record<string, RatioRow>;
}

const LETTER: Record<string, Regime> = { g: "green", s: "sc", v: "vsc", r: "red" };

export function regimeAt(d: DriverAnalysis, lap: number): Regime {
  return LETTER[d.regime[lap - 1] ?? "."] ?? "unknown";
}

export const REGIME_NAME: Record<Regime, string> = {
  green: "green flag",
  sc: "safety car",
  vsc: "virtual safety car",
  red: "red flag",
  unknown: "unknown",
};

export function valueAt(arr: (number | null)[], lap: number): number | null {
  return arr[lap - 1] ?? null;
}

export type GapMetric = "leader" | "interval";

export function gapSeries(doc: AnalysisDoc, driver: string, metric: GapMetric): Point[] {
  const arr = doc.series[driver]?.[metric] ?? [];
  const out: Point[] = [];
  arr.forEach((v, i) => {
    if (v !== null && v !== undefined) out.push({ lap: i + 1, value: v });
  });
  return out;
}

export interface PitNow {
  lap: number;
  regime: Regime;
  position: number | null;
  predicted: number | null;
  fast: number | null;
  slow: number | null;
  loss: number | null;
  margin: number | null;
  stopsNextLap: boolean;
  actualAfter: number | null; 
}

export function pitNowAt(doc: AnalysisDoc, driver: string, lap: number): PitNow | null {
  const d = doc.series[driver];
  if (!d || lap < 1 || lap > doc.laps) return null;
  const stops = doc.stops.some((s) => s.driver === driver && s.lap === lap + 1);
  return {
    lap,
    regime: regimeAt(d, lap),
    position: valueAt(d.pos, lap),
    predicted: valueAt(d.pred, lap),
    fast: valueAt(d.fast, lap),
    slow: valueAt(d.slow, lap),
    loss: valueAt(d.loss, lap),
    margin: valueAt(d.margin, lap),
    stopsNextLap: stops,
    actualAfter: stops ? valueAt(d.pos, lap + 2) : null,
  };
}

export function pitNowSeries(doc: AnalysisDoc, driver: string): { now: Point[]; predicted: Point[]; fast: Point[]; slow: Point[] } {
  const d = doc.series[driver];
  const pick = (arr: (number | null)[]) => {
    const out: Point[] = [];
    (arr ?? []).forEach((v, i) => {
      if (v !== null && v !== undefined) out.push({ lap: i + 1, value: v });
    });
    return out;
  };
  return d ? { now: pick(d.pos), predicted: pick(d.pred), fast: pick(d.fast), slow: pick(d.slow) } : { now: [], predicted: [], fast: [], slow: [] };
}

export function battleRows(doc: AnalysisDoc, includeNeutralised: boolean): Battle[] {
  return doc.battles
    .filter((b) => includeNeutralised || !b.neutralised)
    .slice()
    .sort((a, b) => a.first_lap - b.first_lap || a.attacker.localeCompare(b.attacker));
}

export function battleSummary(rows: Battle[]): { undercut: [number, number]; overcut: [number, number] } {
  const tally = (kind: Battle["kind"]): [number, number] => {
    const k = rows.filter((b) => b.kind === kind);
    return [k.filter((b) => b.attacker_ahead).length, k.length];
  };
  return { undercut: tally("undercut"), overcut: tally("overcut") };
}

export function confidenceNote(regime: Regime, ratios: Record<string, RatioRow>): string | null {
  if (regime === "red") return "No prediction under a red flag: the pit lane is closed and the field queues.";
  if (regime === "green") return null;
  const r = ratios[regime];
  const g = ratios.green;
  const figures =
    r && r.median_loss_s !== null && r.p25_loss_s !== null && r.p75_loss_s !== null
      ? ` Across all circuits a stop under a ${REGIME_NAME[regime]} cost a median ${r.median_loss_s} seconds${g && g.median_loss_s !== null ? ` (green flag: ${g.median_loss_s})` : ""}, and the middle half of measured stops ran from ${r.p25_loss_s} to ${r.p75_loss_s} seconds.`
      : "";
  const part = regime === "vsc" ? " Many of these laps are partly green, which pulls the figure toward the green-flag cost." : "";
  return `Low confidence: the cost of a stop under a ${REGIME_NAME[regime]} is much less certain than under a green flag.${figures}${part}`;
}

export function predictionAt(doc: AnalysisDoc | null, code: string, lapsDone: number): { position: number | null; regime: Regime } | null {
  const d = doc?.series[code];
  if (!d || lapsDone < 1 || lapsDone > doc!.laps) return null;
  return { position: valueAt(d.pred, lapsDone), regime: regimeAt(d, lapsDone) };
}
