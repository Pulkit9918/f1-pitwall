import { describe, expect, it } from "vitest";
import {
  addPick, decodeLap, deltaTo, drawLaps, driversByPace, fastestLap, lapOption, nearestIndex, pickColors, removePick, spreadLabels, statusNote,
  type TraceDriverFile, type TraceLapMeta, type TraceSession,
} from "../lib/traces";

const lapMeta = (o: Partial<TraceLapMeta> & { n: number }): TraceLapMeta => ({ t: 90, ...o });

describe("decoding a lap", () => {
  it("turns centisecond steps into cumulative seconds and the strings into numbers", () => {
    const lap = decodeLap({ dt: [1000, 1250, 999], v: [200, 210, 220, 230], th: [100, 100, 50, 0], g: "5678", d: "00ac", b: "0011" });
    expect(lap.time).toEqual([0, 10, 22.5, 32.49]);
    expect(lap.gear).toEqual([5, 6, 7, 8]);
    expect(lap.brake).toEqual([0, 0, 1, 1]);
    expect(lap.drs).toEqual([0, 0, 1, 1]); // codes 10 (a) and 12 (c) are open, 0 is closed
    expect(lap.speed).toEqual([200, 210, 220, 230]);
  });
  it("leaves the channels null for a lap that has time only", () => {
    const lap = decodeLap({ dt: [500, 500] });
    expect(lap.time).toEqual([0, 5, 10]);
    expect([lap.speed, lap.throttle, lap.brake, lap.gear, lap.drs]).toEqual([null, null, null, null, null]);
  });
  it("measures the delta against a reference point by point", () => {
    const ref = decodeLap({ dt: [1000, 1000] });
    const slow = decodeLap({ dt: [1100, 1000] });
    const fast = decodeLap({ dt: [900, 1050] });
    expect(deltaTo(ref, slow).map((x) => +x.toFixed(2))).toEqual([0, 1, 1]);
    expect(deltaTo(ref, fast).map((x) => +x.toFixed(2))).toEqual([0, -1, -0.5]);
    expect(deltaTo(ref, ref)).toEqual([0, 0, 0]);
  });
});

describe("choosing laps", () => {
  const laps = [lapMeta({ n: 1, r: "standing_start" }), lapMeta({ n: 2, t: 91, k: 1 }), lapMeta({ n: 3, t: 89, k: 0 }), lapMeta({ n: 4, t: 90.5, k: 1 }), lapMeta({ n: 5, t: null, k: 1 })];
  it("takes the quickest trusted traced lap, and the quickest traced lap if none is trusted", () => {
    expect(fastestLap(laps)?.n).toBe(4);
    expect(fastestLap([lapMeta({ n: 3, t: 89, k: 0 }), lapMeta({ n: 6, t: 92, k: 0 }), lapMeta({ n: 1, r: "pit_lap" })])?.n).toBe(3);
    expect(fastestLap([lapMeta({ n: 1, r: "pit_lap" })])).toBeNull();
  });
  it("orders drivers by their best traced lap and drops drivers with none", () => {
    const drivers = [
      { code: "B", team: "", laps: [lapMeta({ n: 2, t: 91, k: 1 })] },
      { code: "A", team: "", laps: [lapMeta({ n: 2, t: 90, k: 1 })] },
      { code: "C", team: "", laps: [lapMeta({ n: 2, r: "pit_lap" })] },
    ];
    expect(driversByPace(drivers)).toEqual(["A", "B"]);
  });
  it("adds each lap once, up to the cap, and removes by driver and lap", () => {
    let p = addPick([], { driver: "A", lap: 2 });
    p = addPick(p, { driver: "A", lap: 2 });
    p = addPick(p, { driver: "A", lap: 3 });
    expect(p).toHaveLength(2);
    expect(addPick(p, { driver: "B", lap: 1 }, 2)).toBe(p);
    expect(removePick(p, { driver: "A", lap: 2 })).toEqual([{ driver: "A", lap: 3 }]);
  });
  it("keeps a lap's colour while it stays chosen and reuses the freed one", () => {
    const a = { driver: "A", lap: 2 }, b = { driver: "B", lap: 2 }, c = { driver: "C", lap: 2 };
    const first = pickColors([a, b], {});
    expect(first).toEqual({ "A:2": 0, "B:2": 1 });
    expect(pickColors([b], first)).toEqual({ "B:2": 1 });
    expect(pickColors([b, c], first)).toEqual({ "B:2": 1, "C:2": 0 });
  });
  it("describes a lap for the picker, with the reason when it has no trace", () => {
    const f = (s: number | null) => (s == null ? "-" : s.toFixed(1));
    expect(lapOption(lapMeta({ n: 7, t: 90.5, c: "HARD", a: 12, s: "4", k: 1 }), f)).toBe("Lap 7 · 90.5 · hard, 12 laps old · safety car");
    expect(lapOption(lapMeta({ n: 8, k: 0 }), f)).toContain("time only");
    expect(lapOption(lapMeta({ n: 1, r: "pit_lap" }), f)).toContain("no trace: pit lap");
    expect(statusNote("1")).toBeNull();
    expect(statusNote("12")).toBe("yellow flag");
  });
});

describe("chart helpers", () => {
  it("finds the nearest grid point", () => {
    const d = [0, 10, 20, 30];
    expect([nearestIndex(d, -5), nearestIndex(d, 4), nearestIndex(d, 6), nearestIndex(d, 29), nearestIndex(d, 99)]).toEqual([0, 0, 1, 3, 3]);
  });
  it("spreads end labels apart, in order, inside the panel", () => {
    expect(spreadLabels([50, 51, 52], 12, 0, 100)).toEqual([50, 62, 74]);
    expect(spreadLabels([0, 1], 12, 0, 100)).toEqual([0, 12]);
    expect(spreadLabels([99, 100], 12, 0, 100)).toEqual([88, 100]);
    expect(spreadLabels([80, 10], 12, 0, 100)).toEqual([80, 10]);
  });
});

describe("drawing laps from the files", () => {
  const session = { points: 3, drivers: [{ code: "A", team: "", laps: [lapMeta({ n: 2, k: 1 })] }] } as unknown as TraceSession;
  const files: Record<string, TraceDriverFile | undefined> = { A: { schema: 1, session_key: "k", driver: "A", points: 3, laps: { "2": { dt: [100, 100] }, "3": { dt: [100] } } } };
  it("draws the laps that are loaded and skips the rest", () => {
    const out = drawLaps([{ driver: "A", lap: 2 }, { driver: "A", lap: 3 }, { driver: "B", lap: 2 }], { "A:2": 4 }, session, files);
    expect(out).toHaveLength(1);
    expect(out[0].slot).toBe(4);
    expect(out[0].meta?.n).toBe(2);
  });
});
