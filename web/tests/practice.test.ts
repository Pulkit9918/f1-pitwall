import { describe, expect, it } from "vitest";
import { fastestLaps, longRuns, runSummary } from "../lib/practice";
import type { SessionDoc } from "../lib/types";

function doc(): SessionDoc {
  const n = null;
  return {
    session: { session_key: "2099-R01-FP2", year: 2099, round: 1, session_code: "FP2", session_name: "Practice 2", event: "X", circuit_id: n, circuit_name: n, country: n, has_laps: true, has_results: true, has_race_control: true },
    drivers: [{ code: "AAA", team: n }, { code: "BBB", team: n }],
    laps: {
      driver_code: ["AAA", "AAA", "AAA", "BBB", "BBB", "CCC"], lap_number: [1, 2, 3, 1, 2, 1],
      stint: [1, 1, 2, 1, 1, 1], compound: ["SOFT", "SOFT", "MEDIUM", "SOFT", "SOFT", n], tyre_life: [1, 2, 1, 3, 4, n],
      position: [n, n, n, n, n, n], track_status: ["1", "1", "1", "1", "1", n], is_green: [true, true, true, true, true, n],
      deleted: [false, false, false, false, true, false], is_accurate: [true, true, true, true, true, n],
      lap_time_s: [91.5, 90.2, 92.0, 91.0, 89.0, n], lap_start_time_s: [n, n, n, n, n, n], time_s: [n, n, n, n, n, n],
      pit_in_time_s: [n, n, n, n, n, n], pit_out_time_s: [n, n, n, n, n, n], sector1_s: [n, n, n, n, n, n], sector2_s: [n, n, n, n, n, n], sector3_s: [n, n, n, n, n, n],
      is_clean_lap: [true, true, true, true, true, n],
    },
    stints: {
      driver_code: ["AAA", "AAA", "BBB", "BBB", "BBB"], stint: [1, 2, 1, 2, 3], compound: ["SOFT", "MEDIUM", "MEDIUM", "MEDIUM", "SOFT"],
      start_lap: [1, 3, 1, 8, 16], end_lap: [2, 12, 7, 15, 17], laps: [2, 10, 7, 8, 2], clean_laps: [2, 8, 6, 3, 1],
      median_clean_lap_s: [90.8, 94.2, 93.9, 95.0, 90.0], degradation_s_per_lap: [n, 0.05, 0.08, n, n],
    },
    pit_stops: { driver_code: [], in_lap: [], pit_in_time_s: [], pit_out_time_s: [], pit_lane_time_s: [], compound_before: [], compound_after: [], is_green_stop: [], position_before: [] },
    race_control_periods: [],
  } as unknown as SessionDoc;
}

describe("practice helpers", () => {
  it("takes each driver's quickest lap that was not deleted and gaps them to the fastest", () => {
    const f = fastestLaps(doc());
    expect(f.map((r) => r.driver)).toEqual(["AAA", "BBB"]); // CCC has no time
    expect(f[0]).toMatchObject({ time: 90.2, lap: 2, compound: "SOFT", tyreAge: 2, gap: 0, laps: 3 });
    expect(f[1]).toMatchObject({ time: 91.0, lap: 1, gap: expect.closeTo(0.8, 6), laps: 1 }); // BBB's 89.0 is deleted
  });
  it("lists long runs by compound, quickest first, with the gap to the quickest on that compound", () => {
    const r = longRuns(doc());
    expect(r.map((g) => g.compound)).toEqual(["MEDIUM"]); // the soft runs are too short, BBB's 3 clean laps are too few
    expect(r[0].runs.map((x) => x.driver)).toEqual(["BBB", "AAA"]);
    expect(r[0].runs[0]).toMatchObject({ pace: 93.9, gap: 0, startLap: 1, endLap: 7 });
    expect(r[0].runs[1].gap).toBeCloseTo(0.3, 6);
    expect(longRuns(doc(), 3).flatMap((g) => g.runs).length).toBe(3); // a lower bar lets BBB's 3-clean-lap run in
  });
  it("counts a driver's runs and how many were long", () => {
    expect(runSummary(doc(), "BBB")).toEqual({ runs: 3, longRuns: 1, laps: 17 });
    expect(runSummary(doc(), "ZZZ")).toEqual({ runs: 0, longRuns: 0, laps: 0 });
  });
});
