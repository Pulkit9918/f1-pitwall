import { describe, expect, it } from "vitest";
import {
  assignSlots,
  cleanSeries,
  driverOrder,
  lapBounds,
  lapDomain,
  periodBands,
  pitRows,
  stintRows,
  timeToLap,
  toggleDriver,
} from "../lib/race";
import { fmtLap, fmtLapTick } from "../lib/format";
import type { SessionDoc } from "../lib/types";

// Two drivers, three laps each. AAA finishes first; BBB retires after lap 2.
function doc(overrides: Partial<SessionDoc> = {}): SessionDoc {
  const n = null;
  return {
    session: {
      session_key: "2099-R01-R", year: 2099, round: 1, session_code: "R", session_name: "Race", event: "Synth GP",
      circuit_id: "synth", circuit_name: "Synth", country: "Australia", has_laps: true, has_results: true, has_race_control: true,
    },
    drivers: [{ code: "AAA", team: "T" }, { code: "BBB", team: "T" }],
    laps: {
      driver_code: ["AAA", "AAA", "AAA", "BBB", "BBB"],
      lap_number: [1, 2, 3, 1, 2],
      stint: [1, 1, 1, 1, 1],
      compound: ["SOFT", "SOFT", "SOFT", "HARD", "HARD"],
      tyre_life: [1, 2, 3, 1, 2],
      position: [1, 1, 1, 2, 2],
      track_status: ["1", "1", "1", "1", "1"],
      is_green: [true, true, true, true, true],
      deleted: [false, false, false, false, false],
      is_accurate: [true, true, true, true, true],
      lap_time_s: [90, 91.5, 90.2, 92, n],
      lap_start_time_s: [0, 90, 181.5, 0, 92],
      time_s: [90, 181.5, 271.7, 92, 184],
      pit_in_time_s: [n, n, n, n, n],
      pit_out_time_s: [n, n, n, n, n],
      sector1_s: [n, n, n, n, n], sector2_s: [n, n, n, n, n], sector3_s: [n, n, n, n, n],
      is_clean_lap: [true, false, true, true, false],
    },
    stints: {
      driver_code: ["AAA", "BBB"], stint: [1, 1], compound: ["SOFT", null], start_lap: [1, 1], end_lap: [3, 2],
      laps: [3, 2], clean_laps: [2, 1], median_clean_lap_s: [90.1, 92], degradation_s_per_lap: [0.05, n],
    },
    pit_stops: {
      driver_code: ["BBB", "AAA"], in_lap: [2, 1], pit_in_time_s: [n, n], pit_out_time_s: [n, n], pit_lane_time_s: [22.5, 23],
      compound_before: ["HARD", "SOFT"], compound_after: ["SOFT", "HARD"], is_green_stop: [true, false], position_before: [2, 1],
    },
    race_control_periods: [
      { period_no: 1, kind: "SC", start_s: 100, end_s: 140, is_open: false, has_session_clock: true },
      { period_no: 2, kind: "VSC", start_s: null, end_s: null, is_open: false, has_session_clock: false },
      { period_no: 3, kind: "RED", start_s: 250, end_s: null, is_open: true, has_session_clock: true },
    ],
    ...overrides,
  };
}

describe("stints and pit stops", () => {
  it("zips columns into rows and names an unknown compound", () => {
    const rows = stintRows(doc());
    expect(rows).toHaveLength(2);
    expect(rows[0]).toMatchObject({ driver: "AAA", compound: "SOFT", startLap: 1, endLap: 3, degradation: 0.05 });
    expect(rows[1].compound).toBe("UNKNOWN");
  });
  it("sorts pit stops by lap", () => {
    expect(pitRows(doc()).map((p) => [p.lap, p.driver, p.green])).toEqual([[1, "AAA", false], [2, "BBB", true]]);
  });
});

describe("driver order", () => {
  it("puts more laps first, then position; falls back to alphabetical without positions", () => {
    expect(driverOrder(doc())).toEqual(["AAA", "BBB"]);
    const d = doc();
    d.laps.position = d.laps.position.map(() => null);
    d.laps.driver_code = ["BBB", "BBB", "BBB", "AAA", "AAA"];
    expect(driverOrder(d)).toEqual(["AAA", "BBB"]);
  });
});

describe("race-control bands on the lap axis", () => {
  it("maps session seconds to fractional laps using the median lap end times", () => {
    const b = lapBounds(doc());
    expect(b.map((x) => x.lap)).toEqual([1, 2, 3]);
    expect(timeToLap(0, b)).toBe(0);
    expect(timeToLap(45, b)).toBeCloseTo(45 / 91, 3); // lap 1 ends at the median of 90 and 92
    expect(timeToLap(1e6, b)).toBe(3);
    expect(timeToLap(5, [])).toBeNull();
  });
  it("skips periods without a session clock and closes an open period at the session end", () => {
    const bands = periodBands(doc());
    expect(bands.map((x) => x.kind)).toEqual(["SC", "RED"]);
    expect(bands[0].x0).toBeGreaterThan(1);
    expect(bands[0].x1).toBeGreaterThan(bands[0].x0);
    expect(bands[1].x1).toBeGreaterThan(bands[1].x0);
  });
});

describe("series and axes", () => {
  it("keeps only clean laps with a time", () => {
    expect(cleanSeries(doc(), "AAA")).toEqual([{ lap: 1, value: 90 }, { lap: 3, value: 90.2 }]);
    expect(cleanSeries(doc(), "BBB")).toEqual([{ lap: 1, value: 92 }]);
  });
  it("sets the lap-time domain from the fastest lap to the 98th percentile", () => {
    const laps = Array.from({ length: 100 }, (_, i) => ({ lap: i + 1, value: 90 + i * 0.01 }));
    laps.push({ lap: 101, value: 200 });   // one slow lap must not flatten the rest
    const [lo, hi] = lapDomain([laps])!;
    expect(lo).toBeLessThan(90);
    expect(hi).toBeGreaterThan(91);
    expect(hi).toBeLessThan(95);
    expect(lapDomain([[]])).toBeNull();
  });
});

describe("driver selection", () => {
  it("caps the selection and keeps colour slots stable", () => {
    let sel: string[] = [];
    for (const c of ["A", "B", "C", "D"]) sel = toggleDriver(sel, c, 3);
    expect(sel).toEqual(["A", "B", "C"]);
    let slots = assignSlots([null, null, null], sel, 3);
    expect(slots).toEqual(["A", "B", "C"]);
    sel = toggleDriver(sel, "B", 3);
    slots = assignSlots(slots, sel, 3);
    expect(slots).toEqual(["A", null, "C"]);
    sel = toggleDriver(sel, "D", 3);
    slots = assignSlots(slots, sel, 3);
    expect(slots).toEqual(["A", "D", "C"]);
  });
});

describe("formatting", () => {
  it("formats lap times", () => {
    expect(fmtLap(92.5)).toBe("1:32.500");
    expect(fmtLap(59.123)).toBe("59.123");
    expect(fmtLap(null)).toBe("-");
    expect(fmtLapTick(92.5)).toBe("1:32.5");
  });
});
