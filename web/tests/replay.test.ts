import { describe, expect, it } from "vitest";
import {
  buildLapIndex,
  channelAt,
  cumAt,
  decodeReplay,
  driverFacts,
  fmtClock,
  fmtGap,
  frame,
  gapsToDriver,
  hasData,
  inPit,
  lapEnds,
  lapHistory,
  lapsDoneAt,
  lapStartTime,
  leaderLap,
  messagesUpTo,
  qualiBoard,
  raceBoard,
  statusAt,
  timeAtCum,
  timeBands,
  timingRows,
  trackPoint,
  tyreAt,
  weatherAt,
  type LapIndex,
  type LapRec,
  type ReplayFile,
} from "../lib/replay";
import type { SessionDoc } from "../lib/types";
import { contrastWith, teamFill } from "../lib/colors";

// 41 frames, one a second. Progress is in 1e-4 laps. A: 0.10 lap/s from -0.05. B: 0.08 lap/s from -0.10.
// C: 0.04 lap/s from -0.20, so it is more than a lap behind A by t = 30.
const N = 41;
const dp = (v: number) => Array(N - 1).fill(v);
const file: ReplayFile = {
  schema: 1,
  key: "2099-R01-R",
  kind: "race",
  t0: 0,
  step: 1,
  n: N,
  track: { w: 100, h: 100, pts: [[0, 0], [100, 0], [100, 100], [0, 100]] },
  drivers: {
    AAA: { num: 1, a: 0, b: 40, p0: -500, dp: dp(1000), spd: Array(N).fill(250), gear: Array(N).fill(7), thr: Array(N).fill(100), brk: Array(N).fill(0), drs: Array(N).fill(12) },
    BBB: { num: 2, a: 0, b: 40, p0: -1000, dp: dp(800) },
    CCC: { num: 3, a: 5, b: 40, p0: -2000, dp: dp(400) },
  },
  weather: { t: [0, 20, 40], air: [20, 21, 22], track: [30, 31, 32], humidity: [50, 51, 52], rain: [0, 0, 1], wind: [1, 2, 3], wind_dir: [90, 100, 110] },
  messages: [[5, "Flag", "YELLOW", 1, "YELLOW IN TURN 3", null], [12, "Other", "", 2, "CAR 2 (BBB) DELETED", "BBB"], [30, "Flag", "GREEN", 3, "CLEAR", null]],
  track_status: [[0, "1", "AllClear"], [8, "2", "Yellow"], [14, "1", "AllClear"]],
};
const r = decodeReplay(file);
const OPTS = { total: 3, start: 0.5 };

const lap = (n: number, start: number | null, end: number | null, extra: Partial<LapRec> = {}): LapRec => ({
  lap: n, start, end, time: start != null && end != null ? end - start : null, s1: null, s2: null, s3: null,
  compound: "MEDIUM", tyreLife: n, pitIn: null, pitOut: null, deleted: false, ...extra,
});
const idx: LapIndex = new Map([
  ["AAA", [lap(1, 0.5, 10.5, { s1: 3, s2: 4, s3: 3 }), lap(2, 10.5, 20.4, { s1: 3.1, s2: 3.9, s3: 2.9, pitIn: 19 }), lap(3, 20.4, 30.4, { compound: "HARD", tyreLife: 1, pitOut: 22, s1: 3.2, s2: 4.1, s3: 2.7 })]],
  ["BBB", [lap(1, 1, 13.5, { s1: 3.5, s2: 4.5, s3: 4.5 }), lap(2, 13.5, 26, { s1: 3.3, s2: 4.2, s3: 3.9 }), lap(3, 26, null)]],
  ["CCC", [lap(1, 5, 30, { s1: 9, s2: 9, s3: 7 })]],
]);

describe("decoding and sampling", () => {
  it("rebuilds progress from the starting value and the steps", () => {
    expect(r.cum.AAA[0]).toBeCloseTo(-0.05);
    expect(r.cum.AAA[10]).toBeCloseTo(0.95);
    expect(r.end).toBe(40);
  });
  it("keeps a never-decreasing copy for gaps", () => {
    const f2 = { ...file, drivers: { X: { num: 9, a: 0, b: 4, p0: 0, dp: [1000, -500, 1000, 1000] } }, n: 5 };
    const d = decodeReplay(f2);
    expect(Array.from(d.cum.X)).toEqual([0, 0.1, 0.05, 0.15, 0.25].map((v) => expect.closeTo(v, 6)));
    expect(Array.from(d.mono.X)).toEqual([0, 0.1, 0.1, 0.15, 0.25].map((v) => expect.closeTo(v, 6)));
  });
  it("interpolates between frames and clamps outside the file", () => {
    expect(cumAt(r, "AAA", 2.5)).toBeCloseTo(0.2);
    expect(cumAt(r, "AAA", -10)).toBeCloseTo(-0.05);
    expect(cumAt(r, "AAA", 999)).toBeCloseTo(3.95);
    expect(frame(r, 40)).toEqual({ i: 39, f: 1 });
  });
  it("knows when a car has data", () => {
    expect(hasData(r, "CCC", 3)).toBe(false);
    expect(hasData(r, "CCC", 5)).toBe(true);
    expect(hasData(r, "ZZZ", 5)).toBe(false);
  });
  it("finds when a car reached a distance", () => {
    expect(timeAtCum(r, "AAA", 0.5)).toBeCloseTo(5.5);
    expect(timeAtCum(r, "AAA", -1)).toBe(0);
    expect(timeAtCum(r, "AAA", 99)).toBeNull();
  });
  it("walks round the outline and wraps", () => {
    const pts = file.track.pts;
    expect(trackPoint(pts, 0)).toEqual([0, 0]);
    expect(trackPoint(pts, 0.125)).toEqual([50, 0]);
    expect(trackPoint(pts, 1.125)).toEqual([50, 0]);
    expect(trackPoint(pts, -0.875)).toEqual([50, 0]);
    expect(trackPoint(pts, 0.875)).toEqual([0, 50]);
  });
  it("reads the car channels at the nearest frame", () => {
    expect(channelAt(r, "AAA", 3.4)).toEqual({ speed: 250, gear: 7, throttle: 100, brake: false, drs: 12 });
    expect(channelAt(r, "BBB", 3)).toBeNull();
  });
});

describe("race leaderboard", () => {
  const facts = driverFacts(idx);
  it("orders by progress and gives gaps from the time the car ahead was at the same point", () => {
    const rows = raceBoard(r, facts, 15, OPTS);
    expect(rows.map((x) => x.code)).toEqual(["AAA", "BBB", "CCC"]);
    expect(rows[0]).toMatchObject({ pos: 1, gapLeader: "Leader", interval: "" });
    // BBB is at 0.08*15-0.1 = 1.1 laps; AAA was there at (1.1+0.05)/0.1 = 11.5 s
    expect(rows[1].gapLeader).toBe("+3.500");
    expect(rows[1].interval).toBe("+3.500");
  });
  it("shows laps down once the leader is a lap or more ahead", () => {
    const rows = raceBoard(r, facts, 36, OPTS);
    expect(rows[2].code).toBe("CCC");
    expect(rows[2].gapLeader).toBe("+2 LAPS");
  });
  it("marks a car whose last lap never finished as out, after half a lap", () => {
    // its last lap starts at 26 and the median lap is 12.5 s, so it shows as out from 32.25
    expect(raceBoard(r, facts, 33, OPTS).find((x) => x.code === "BBB")!.state).toBe("out");
    expect(raceBoard(r, facts, 30, OPTS).find((x) => x.code === "BBB")!.state).toBe("run");
  });
  it("leaves the gaps blank before the start", () => {
    const rows = raceBoard(r, facts, 0.2, OPTS);
    expect(rows.every((x) => x.gapLeader === "" && x.interval === "")).toBe(true);
  });
  it("treats a car that stopped three or more laps short as out, even with no unfinished lap", () => {
    // a lap table where CCC finished lap 1 (at 30) while the winner did 4 laps
    const short: LapIndex = new Map([["AAA", idx.get("AAA")!], ["CCC", [lap(1, 5, 30)]]]);
    const f2 = driverFacts(short);
    const o = { total: 4, start: 0.5 };
    // its lap took 25 s and ended at 30, so it shows as out from 30 + 0.75 * 25 = 48.75
    expect(raceBoard(r, f2, 40, o).find((x) => x.code === "CCC")!.state).not.toBe("out");
    expect(raceBoard(r, f2, 49, o).find((x) => x.code === "CCC")!.state).toBe("out");
    expect(raceBoard(r, f2, 49, { total: 3, start: 0.5 }).find((x) => x.code === "CCC")!.state).not.toBe("out");
  });
  it("freezes finished cars at their lap count and order", () => {
    const rows = raceBoard(r, facts, 40, OPTS);
    expect(rows[0]).toMatchObject({ code: "AAA", state: "fin", progress: 3 });
  });
  it("reports pit stops from pit-in on one lap to pit-out on the next", () => {
    const recs = idx.get("AAA")!;
    expect(inPit(recs, 18)).toBe(false);
    expect(inPit(recs, 20)).toBe(true);
    expect(inPit(recs, 22.1)).toBe(false);
    expect(raceBoard(r, facts, 20, OPTS).find((x) => x.code === "AAA")!.state).toBe("pit");
  });
  it("gives the tyre in use and the stops made so far", () => {
    expect(tyreAt(idx.get("AAA")!, 5)).toEqual({ compound: "MEDIUM", life: 1, stops: 0 });
    expect(tyreAt(idx.get("AAA")!, 25)).toEqual({ compound: "HARD", life: 1, stops: 1 });
  });
});

describe("qualifying board and timing table", () => {
  const facts = driverFacts(idx);
  it("orders by best lap so far", () => {
    const rows = qualiBoard(facts, 14);
    expect(rows.map((x) => x.code)).toEqual(["AAA", "BBB", "CCC"]);
    expect(rows[0]).toMatchObject({ best: 10, gapLeader: "Leader" });
    expect(rows[1].gapLeader).toBe("+2.500");
    expect(rows[2].gapLeader).toBe("");           // no completed lap yet
    expect(qualiBoard(facts, 31).map((x) => x.code)).toEqual(["AAA", "BBB", "CCC"]);
  });
  it("marks purple for the best so far and green for a driver's own best", () => {
    const rows = timingRows(idx, ["AAA", "BBB", "CCC"], 27);
    const a = rows[0];
    const b = rows[1];
    // AAA laps: 10, 9.9, 10 (the third runs 20.4 to 30.4 and is not complete by 27), so two are done and the best is 9.9
    expect(a.laps).toBe(2);
    expect(a.best.v).toBeCloseTo(9.9);
    expect(a.best.purple).toBe(true);
    expect(a.last.v).toBeCloseTo(9.9);
    expect(a.last).toMatchObject({ purple: true, green: false });
    expect(a.sectors[0]).toMatchObject({ v: 3.1, purple: false, green: false });   // 3.0 on lap 1 is faster
    expect(a.sectors[1]).toMatchObject({ v: 3.9, purple: true });
    expect(b.last).toMatchObject({ v: 12.5, purple: false, green: true });
    expect(b.sectors[2]).toMatchObject({ v: 3.9, purple: false, green: true });
  });
  it("leaves deleted laps out of the bests", () => {
    const deleted: LapIndex = new Map([["AAA", [lap(1, 0, 10, { deleted: true }), lap(2, 10, 21)]]]);
    const rows = timingRows(deleted, ["AAA"], 30);
    expect(rows[0].best.v).toBe(11);
  });
});

describe("clock, laps, weather, messages and bands", () => {
  it("formats times and gaps", () => {
    expect(fmtClock(4363)).toBe("1:12:43");
    expect(fmtClock(65)).toBe("1:05");
    expect(fmtClock(-12)).toBe("-0:12");
    expect(fmtGap(3.5)).toBe("+3.500");
    expect(fmtGap(125.25)).toBe("+125.3");
    expect(fmtGap(null)).toBe("");
  });
  it("works out the leader's lap from lap end times", () => {
    const ends = lapEnds(idx);
    expect(ends).toEqual([10.5, 20.4, 30.4]);
    expect(leaderLap(ends, 0, 3)).toBe(1);
    expect(leaderLap(ends, 10.5, 3)).toBe(2);
    expect(leaderLap(ends, 99, 3)).toBe(3);
  });
  it("reads the weather at a time", () => {
    expect(weatherAt(file.weather, 25)).toMatchObject({ air: 21, track: 31, rain: false, wind: 2 });
    expect(weatherAt(file.weather, 45)).toMatchObject({ air: 22, rain: true });
    expect(weatherAt(null, 5)).toBeNull();
  });
  it("lists messages so far, newest first", () => {
    expect(messagesUpTo(file, 13).map((m) => m[4])).toEqual(["CAR 2 (BBB) DELETED", "YELLOW IN TURN 3"]);
    expect(messagesUpTo(file, 1)).toEqual([]);
    expect(messagesUpTo(file, 99, 1).map((m) => m[4])).toEqual(["CLEAR"]);
  });
  it("reads the track status", () => {
    expect(statusAt(file, 9)).toEqual({ code: "2", label: "Yellow" });
    expect(statusAt(file, 20)).toEqual({ code: "1", label: "AllClear" });
  });
  it("builds timeline bands from track status and the gold periods", () => {
    const doc = { race_control_periods: [{ period_no: 1, kind: "SC", start_s: 30, end_s: null, is_open: true, has_session_clock: true }, { period_no: 2, kind: "VSC", start_s: null, end_s: null, is_open: false, has_session_clock: false }] } as unknown as SessionDoc;
    expect(timeBands(r, doc)).toEqual([
      { kind: "YELLOW", t0: 8, t1: 14 },
      { kind: "SC", t0: 30, t1: 40 },
    ]);
    expect(timeBands(r, null)).toEqual([{ kind: "YELLOW", t0: 8, t1: 14 }]);
  });
});

describe("lap index from a session document", () => {
  it("zips the columns, derives a missing lap end and sorts by lap", () => {
    const col = (v: unknown[]) => v;
    const doc = {
      laps: {
        driver_code: col(["VER", "VER"]), lap_number: col([2, 1]), stint: col([1, 1]), compound: col(["HARD", "HARD"]),
        tyre_life: col([2, 1]), position: col([1, 1]), track_status: col(["1", "1"]), is_green: col([true, true]),
        deleted: col([false, true]), is_accurate: col([true, true]), lap_time_s: col([90, 91]), lap_start_time_s: col([91, 0]),
        time_s: col([null, 91]), pit_in_time_s: col([null, null]), pit_out_time_s: col([null, null]),
        sector1_s: col([30, 30]), sector2_s: col([30, 30]), sector3_s: col([30, 31]), is_clean_lap: col([true, true]),
      },
    } as unknown as SessionDoc;
    const built = buildLapIndex(doc).get("VER")!;
    expect(built.map((l) => l.lap)).toEqual([1, 2]);
    expect(built[1].end).toBe(181);
    expect(built[0].deleted).toBe(true);
  });
});

describe("team colours", () => {
  it("keeps a colour that is already visible, and lightens one that is too dark", () => {
    expect(teamFill("#FF8000")).toBe("#ff8000");
    const dark = teamFill("#0B1F4A")!;
    expect(dark).not.toBe("#0b1f4a");
    expect(contrastWith(dark)).toBeGreaterThanOrEqual(3);
    expect(contrastWith("#0B1F4A")).toBeLessThan(3);
  });
  it("gives nothing for a missing or malformed colour", () => {
    expect(teamFill(null)).toBeNull();
    expect(teamFill("zzz")).toBeNull();
    expect(teamFill("3671C6")).toBeNull();
  });
  it("marks the higher car number of a team as its second car", () => {
    const f = { ...file, teams: { AAA: ["Ferrari", "#E80020"], BBB: ["Ferrari", "#E80020"], CCC: ["Haas", null] } } as ReplayFile;
    const d = decodeReplay(f);
    expect(d.teams.AAA).toEqual({ name: "Ferrari", color: "#E80020", second: false });
    expect(d.teams.BBB.second).toBe(true);
    expect(d.teams.CCC).toEqual({ name: "Haas", color: null, second: false });
  });
  it("has no teams when the file has none", () => {
    expect(decodeReplay(file).teams).toEqual({});
  });
});

describe("gap to a chosen driver", () => {
  const facts = driverFacts(idx);
  it("is plus for cars behind the driver and minus for cars ahead, by the same method as the board", () => {
    const rows = raceBoard(r, facts, 15, OPTS);
    const g = gapsToDriver(r, rows, 15, "BBB", OPTS.start);
    expect(g.get("BBB")).toBe("Selected");
    expect(g.get("AAA")).toBe("-3.500");       // A was where B is now 11.5 s in; 15 - 11.5
    expect(g.get("CCC")).toBe("+8.750");       // B was where C is now 6.25 s in; 15 - 6.25
  });
  it("shows whole laps when a car is a lap or more apart", () => {
    const rows = raceBoard(r, facts, 36, OPTS);
    const g = gapsToDriver(r, rows, 36, "AAA", OPTS.start);
    expect(g.get("CCC")).toMatch(/^\+\d LAPS?$/);
    const back = gapsToDriver(r, rows, 36, "CCC", OPTS.start);
    expect(back.get("AAA")).toMatch(/^-\d LAPS?$/);
  });
  it("is blank before the start and empty for a driver that is not on the board", () => {
    const rows = raceBoard(r, facts, 0.2, OPTS);
    expect(gapsToDriver(r, rows, 0.2, "AAA", OPTS.start).get("BBB")).toBe("");
    expect(gapsToDriver(r, rows, 0.2, "ZZZ", OPTS.start).size).toBe(0);
  });
});

describe("laps done, lap start and lap history", () => {
  it("counts the last lap finished by a time", () => {
    expect(lapsDoneAt(idx.get("AAA")!, 5)).toBe(0);
    expect(lapsDoneAt(idx.get("AAA")!, 10.5)).toBe(1);
    expect(lapsDoneAt(idx.get("AAA")!, 25)).toBe(2);
    expect(lapsDoneAt(idx.get("BBB")!, 99)).toBe(2);     // lap 3 never finished
  });
  it("starts lap 1 at the race start and lap n at the end of lap n - 1", () => {
    const ends = lapEnds(idx);
    expect(lapStartTime(ends, 1, 0.5)).toBe(0.5);
    expect(lapStartTime(ends, 2, 0.5)).toBe(ends[0]);
    expect(lapStartTime(ends, 99, 0.5)).toBeNull();
  });
  it("lists finished laps newest first for the chosen drivers only, and marks the bests", () => {
    const h = lapHistory(idx, ["AAA", "BBB"], 26);
    expect(h.laps).toEqual([2, 1]);
    expect(h.rows.get(2)!.has("CCC")).toBe(false);
    expect(h.sessionBest).toBeCloseTo(9.9);               // A's lap 2: 20.4 - 10.5
    expect(h.own.get("BBB")).toBeCloseTo(12.5);
    expect(lapHistory(idx, ["AAA"], 5).laps).toEqual([]);
  });
  it("ignores laps the stewards deleted when finding the best", () => {
    const idx2: LapIndex = new Map([["AAA", [lap(1, 0, 8, { deleted: true }), lap(2, 8, 20)]]]);
    expect(lapHistory(idx2, ["AAA"], 30).sessionBest).toBeCloseTo(12);
  });
});
