// Types and small pure helpers for the season pages (data from scripts/export_seasons.py).

export interface SeasonIndexEntry {
  season: number;
  rounds: number;
  champion: string | null;
  champion_id: string | null;
  champion_points: number | null;
  constructor_champion: string | null;
  constructor_points: number | null;
}
export interface SeasonIndex { generator: string; schema: number; seasons: SeasonIndexEntry[] }

export interface DriverStanding { position: number; driver_id: string; name: string; team: string | null; points: number | null; wins: number }
export interface ConstructorStanding { position: number; constructor_id: string; name: string; points: number | null; wins: number }
export interface RaceResult {
  position: number | null; driver_id: string; code: string | null; name: string; constructor_id: string | null; team: string | null;
  grid: number | null; points: number | null; laps: number | null; status: string | null; classified: boolean; gained: number | null; fastest: boolean;
}
export interface SeasonRace { round: number; name: string; date: string | null; circuit_id: string | null; podium: string[]; results: RaceResult[] }
export interface DriverSeries { driver_id: string; code: string; name: string; cum: (number | null)[]; pos: number[]; imputed: boolean }
export interface ConstructorSeries { constructor_id: string; name: string; cum: (number | null)[]; pos: number[] }
export interface SeasonDoc {
  schema: number; season: number; drivers: DriverStanding[]; constructors: ConstructorStanding[]; races: SeasonRace[];
  progression: { rounds: number[]; drivers: DriverSeries[]; constructors: ConstructorSeries[] };
}

export function gainedLabel(g: number | null): string {
  if (g === null) return "–";
  if (g > 0) return `+${g}`;
  if (g < 0) return `−${Math.abs(g)}`;
  return "0";
}

export function lastName(full: string): string {
  const parts = full.trim().split(/\s+/);
  return parts[parts.length - 1] ?? full;
}

export function podiumNames(race: SeasonRace): string[] {
  return race.results.filter((r) => r.position !== null && r.position <= 3).sort((a, b) => a.position! - b.position!).map((r) => lastName(r.name));
}

export function biggestMovers(race: SeasonRace): { gain: RaceResult | null; loss: RaceResult | null } {
  const moved = race.results.filter((r) => r.classified && r.gained !== null);
  const gain = moved.reduce<RaceResult | null>((b, r) => (r.gained! > 0 && (!b || r.gained! > b.gained!) ? r : b), null);
  const loss = moved.reduce<RaceResult | null>((b, r) => (r.gained! < 0 && (!b || r.gained! < b.gained!) ? r : b), null);
  return { gain, loss };
}

export interface RoundPoint { round: number; value: number }

export function seriesPoints(rounds: number[], values: (number | null)[]): RoundPoint[] {
  const out: RoundPoint[] = [];
  rounds.forEach((round, i) => {
    const v = values[i];
    if (v !== null && v !== undefined) out.push({ round, value: v });
  });
  return out;
}
