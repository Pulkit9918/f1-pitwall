export function fmtLap(s: number | null | undefined): string {
  if (s == null || !Number.isFinite(s)) return "-";
  const m = Math.floor(s / 60);
  const rest = s - m * 60;
  const sec = rest.toFixed(3).padStart(6, "0");
  return m > 0 ? `${m}:${sec}` : rest.toFixed(3);
}

// A y-axis tick for lap times: 1:32.5 or 92.5
export function fmtLapTick(s: number): string {
  const m = Math.floor(s / 60);
  const rest = s - m * 60;
  return m > 0 ? `${m}:${rest.toFixed(1).padStart(4, "0")}` : rest.toFixed(1);
}

export function fmtSeconds(s: number | null | undefined, digits = 1): string {
  return s == null || !Number.isFinite(s) ? "-" : `${s.toFixed(digits)} s`;
}

export function fmtDeg(s: number | null | undefined): string {
  if (s == null || !Number.isFinite(s)) return "-";
  const sign = s > 0 ? "+" : s < 0 ? "-" : "";
  return `${sign}${Math.abs(s).toFixed(3)} s/lap`;
}

export const SESSION_NAMES: Record<string, string> = {
  R: "Race",
  Q: "Qualifying",
  S: "Sprint",
  SQ: "Sprint qualifying",
  SS: "Sprint shootout",
  FP1: "Practice 1",
  FP2: "Practice 2",
  FP3: "Practice 3",
};

export function sessionLabel(code: string, name?: string | null): string {
  return name || SESSION_NAMES[code] || code;
}

export function isPractice(code: string): boolean {
  return code.startsWith("FP");
}
