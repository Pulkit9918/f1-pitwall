// The shapes written by scripts/export_static.py (web/public/data). Tables are stored column by column.

export type Maybe<T> = T | null;

export interface SessionMeta {
  session_key: string;
  year: number;
  round: number;
  session_code: string;
  session_name: string;
  event: string;
  circuit_id: Maybe<string>;
  circuit_name: Maybe<string>;
  country: Maybe<string>;
  has_laps: boolean;
  has_results: boolean;
  has_race_control: boolean;
}

export interface LapCols {
  driver_code: string[];
  lap_number: number[];
  stint: Maybe<number>[];
  compound: Maybe<string>[];
  tyre_life: Maybe<number>[];
  position: Maybe<number>[];
  track_status: Maybe<string>[];
  is_green: Maybe<boolean>[];
  deleted: Maybe<boolean>[];
  is_accurate: Maybe<boolean>[];
  lap_time_s: Maybe<number>[];
  lap_start_time_s: Maybe<number>[];
  time_s: Maybe<number>[];
  pit_in_time_s: Maybe<number>[];
  pit_out_time_s: Maybe<number>[];
  sector1_s: Maybe<number>[];
  sector2_s: Maybe<number>[];
  sector3_s: Maybe<number>[];
  is_clean_lap: Maybe<boolean>[];
}

export interface StintCols {
  driver_code: string[];
  stint: number[];
  compound: Maybe<string>[];
  start_lap: Maybe<number>[];
  end_lap: Maybe<number>[];
  laps: Maybe<number>[];
  clean_laps: Maybe<number>[];
  median_clean_lap_s: Maybe<number>[];
  degradation_s_per_lap: Maybe<number>[];
}

export interface PitCols {
  driver_code: string[];
  in_lap: Maybe<number>[];
  pit_in_time_s: Maybe<number>[];
  pit_out_time_s: Maybe<number>[];
  pit_lane_time_s: Maybe<number>[];
  compound_before: Maybe<string>[];
  compound_after: Maybe<string>[];
  is_green_stop: Maybe<boolean>[];
  position_before: Maybe<number>[];
}

export type PeriodKind = "SC" | "VSC" | "RED";

export interface Period {
  period_no: number;
  kind: PeriodKind;
  start_s: Maybe<number>;
  end_s: Maybe<number>;
  is_open: boolean;
  has_session_clock: boolean;
}

export interface SessionDoc {
  session: SessionMeta;
  drivers: { code: string; team: Maybe<string> }[];
  laps: LapCols;
  stints: StintCols;
  pit_stops: PitCols;
  race_control_periods: Period[];
}

export interface PitLoss {
  stops: number;
  sessions: number;
  seasons: number;
  median_pit_loss_s: Maybe<number>;
  p25_pit_loss_s: Maybe<number>;
  p75_pit_loss_s: Maybe<number>;
  is_reliable: boolean;
}

export interface DegradationRow {
  circuit_layout_key: string;
  layout_id: Maybe<string>;
  compound: string;
  stints: number;
  races: number;
  seasons: number;
  median_degradation_s_per_lap: Maybe<number>;
  p25_degradation_s_per_lap: Maybe<number>;
  p75_degradation_s_per_lap: Maybe<number>;
  approx_se_median_s_per_lap: Maybe<number>;
  is_reliable: boolean;
}

export interface Circuit {
  circuit_id: string;
  circuit_name: string;
  locality: Maybe<string>;
  country: Maybe<string>;
  lat: Maybe<number>;
  long: Maybe<number>;
  pit_loss: Maybe<PitLoss>;
  degradation: DegradationRow[];
}

export interface Manifest {
  generated_utc: string;
  from_year: number;
  sessions: number;
  session_files: number;
  circuits: number;
  seasons: number[];
}

// One row per tyre stint, after the columns are zipped back together.
export interface Stint {
  driver: string;
  stint: number;
  compound: string;
  startLap: number;
  endLap: number;
  laps: number;
  cleanLaps: number;
  medianCleanLap: Maybe<number>;
  degradation: Maybe<number>;
}

export interface PitStop {
  driver: string;
  lap: number;
  pitLane: Maybe<number>;
  before: Maybe<string>;
  after: Maybe<string>;
  green: boolean;
  positionBefore: Maybe<number>;
}

// A race-control period in lap units: lap n spans [n - 1, n].
export interface LapBand {
  kind: PeriodKind;
  x0: number;
  x1: number;
}

export interface Point {
  lap: number;
  value: number;
}
