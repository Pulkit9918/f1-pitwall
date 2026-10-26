// How well the pit-now prediction matched real stops, as written by scripts/export_predictor.py.

export interface ScoreRow {
  scope: "all" | "undisturbed";
  regime: string;
  margin: string;
  stops: number;
  hit: number | null;
  within_one: number | null;
  mae: number | null;
  bias: number | null;
  in_range: number | null;
  no_loss_hit: number | null;
  no_loss_mae: number | null;
  global_hit: number | null;
  global_mae: number | null;
  reliable: boolean;
}

export interface ScoreDoc {
  schema: number;
  rows: ScoreRow[];
}

export interface StopsDoc {
  schema: number;
  sessions: { key: string; year: number; round: number; event: string | null }[];
  s: number[];
  d: string[];
  l: number[];
  r: string[]; // g green, s safety car, v virtual safety car
  n: number[]; // position before the stop
  p: number[]; // predicted position
  f: number[]; // predicted with a quick stop
  w: number[]; // predicted with a slow stop
  a: number[]; // actual position at the end of the out-lap
  m: (number | null)[]; // margin in seconds
  o: number[]; // other drivers' stops nearby
}

export interface StopRow {
  driver: string;
  lap: number;
  regime: string;
  before: number;
  predicted: number;
  fast: number;
  slow: number;
  actual: number;
  margin: number | null;
  disturbed: boolean;
}

export const REGIME_NAME: Record<string, string> = { g: "green flag", s: "safety car", v: "virtual safety car" };

export const MARGIN_ORDER = ["under 1 s", "1 to 3 s", "over 3 s", "no margin"];

export function pct(x: number | null | undefined, digits = 0): string {
  return x == null || !Number.isFinite(x) ? "-" : `${(x * 100).toFixed(digits)}%`;
}

export function places(x: number | null | undefined): string {
  return x == null || !Number.isFinite(x) ? "-" : x.toFixed(2);
}

export function signedPlaces(x: number | null | undefined): string {
  return x == null || !Number.isFinite(x) ? "-" : `${x > 0 ? "+" : x < 0 ? "-" : ""}${Math.abs(x).toFixed(2)}`;
}

export function overall(rows: ScoreRow[], scope: ScoreRow["scope"]): ScoreRow | undefined {
  return rows.find((r) => r.scope === scope && r.regime === "all" && r.margin === "all");
}

export function byRegime(rows: ScoreRow[], scope: ScoreRow["scope"]): ScoreRow[] {
  const order = ["green", "sc", "vsc"];
  return rows.filter((r) => r.scope === scope && r.regime !== "all" && r.margin === "all").sort((a, b) => order.indexOf(a.regime) - order.indexOf(b.regime));
}

export function byMargin(rows: ScoreRow[], scope: ScoreRow["scope"]): ScoreRow[] {
  return rows
    .filter((r) => r.scope === scope && r.margin !== "all" && r.regime === "all")
    .sort((a, b) => MARGIN_ORDER.indexOf(a.margin) - MARGIN_ORDER.indexOf(b.margin));
}

export function stopRows(doc: StopsDoc, session: number): StopRow[] {
  const out: StopRow[] = [];
  for (let i = 0; i < doc.s.length; i++) {
    if (doc.s[i] !== session) continue;
    out.push({ driver: doc.d[i], lap: doc.l[i], regime: doc.r[i], before: doc.n[i], predicted: doc.p[i], fast: doc.f[i], slow: doc.w[i], actual: doc.a[i], margin: doc.m[i], disturbed: doc.o[i] > 0 });
  }
  return out;
}

// What the model's range said about the real outcome.
export function verdict(r: StopRow): "exact" | "in range" | "outside" {
  if (r.predicted === r.actual) return "exact";
  return r.actual >= r.fast && r.actual <= r.slow ? "in range" : "outside";
}

export function sessionsWithStops(doc: StopsDoc): { index: number; count: number }[] {
  const counts = new Map<number, number>();
  for (const s of doc.s) counts.set(s, (counts.get(s) ?? 0) + 1);
  return [...counts].map(([index, count]) => ({ index, count })).sort((a, b) => a.index - b.index);
}
