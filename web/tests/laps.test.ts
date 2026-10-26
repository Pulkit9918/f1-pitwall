import { describe, expect, it } from "vitest";
import { driversByBest, isRaceLike, lapRows, median, pairedLaps, summarise, type LapDoc, type LapDriver } from "../lib/laps";

const driver = (code: string, o: Partial<LapDriver> = {}): LapDriver => ({
  code, team: "", n: [1, 2, 3], t: [90, 88, 89], s1: [30, 29, 29.5], s2: [35, 34, 34.2], s3: [25, 25, 25.3],
  c: ["ppp", "ppy", "yyy"], k: ["SOFT", "SOFT", "SOFT"], a: [1, 2, 3], w: ["1", "1", "1"], o: [1, 1, 1], i: [0, 0, 0], x: [0, 0, 0], ...o,
});

describe("lap rows and summaries", () => {
  it("turns the columns into rows with colours", () => {
    const rows = lapRows(driver("A", { c: ["pg-", "yyy", "---"] }));
    expect(rows[0].colours).toEqual(["purple", "green", "none"]);
    expect(rows[1].colours).toEqual(["yellow", "yellow", "yellow"]);
    expect(rows[0]).toMatchObject({ n: 1, time: 90, sectors: [30, 35, 25], compound: "SOFT", age: 1, clean: true, pit: false, deleted: false });
  });
  it("takes medians of odd and even counts and nothing from nothing", () => {
    expect([median([3, 1, 2]), median([4, 1, 2, 3]), median([])]).toEqual([2, 2.5, null]);
  });
  it("finds the best lap, the best sectors and the lap they add up to", () => {
    const s = summarise(lapRows(driver("A")));
    expect(s.best).toBe(88);
    expect(s.bestSectors).toEqual([29, 34, 25]);
    expect(s.theoretical).toBe(88);
    expect(s.medianClean).toBe(89);
    expect(s.purple).toBe(5);
    expect(s.laps).toBe(3);
  });
  it("leaves out deleted laps, and keeps pit and unclean laps out of the clean median", () => {
    const rows = lapRows(driver("A", { x: [0, 1, 0], i: [1, 0, 0], o: [1, 1, 0], t: [120, 80, 89] }));
    const s = summarise(rows);
    expect(s.laps).toBe(2);
    expect(s.best).toBe(89); // the deleted 80 does not count
    expect(s.clean).toBe(0);
    expect(s.medianClean).toBeNull();
    expect(s.purple).toBe(3); // the deleted lap's colours do not count either
  });
  it("has no theoretical best when a sector was never timed", () => {
    expect(summarise(lapRows(driver("A", { s3: [null, null, null] }))).theoretical).toBeNull();
  });
});

describe("pairing laps", () => {
  it("matches clean laps by number and subtracts the second driver from the first", () => {
    const a = lapRows(driver("A"));
    const b = lapRows(driver("B", { t: [91, 87, 90], s1: [30.5, 28.5, 30], s2: [35, 34, 34.5], s3: [25.5, 24.5, 25.5] }));
    const p = pairedLaps(a, b);
    expect(p.map((x) => x.n)).toEqual([1, 2, 3]);
    expect(p[1].lap).toBeCloseTo(1);
    expect(p[1].sectors.map((x) => +x.toFixed(2))).toEqual([0.5, 0, 0.5]);
    expect(p[0].sectors.map((x) => +x.toFixed(2))).toEqual([-0.5, 0, -0.5]);
  });
  it("skips a lap either driver did not drive cleanly", () => {
    const a = lapRows(driver("A", { i: [0, 1, 0] }));
    const b = lapRows(driver("B", { o: [1, 1, 0], s2: [35, null, 34] }));
    expect(pairedLaps(a, b).map((x) => x.n)).toEqual([1]);
  });
});

describe("ordering drivers", () => {
  it("lists drivers by best lap and drops those with none", () => {
    const doc = { drivers: [driver("B", { t: [92, 91, 93] }), driver("A"), driver("C", { t: [null, null, null] })] } as unknown as LapDoc;
    expect(driversByBest(doc)).toEqual(["A", "B"]);
    expect([isRaceLike("R"), isRaceLike("S"), isRaceLike("Q")]).toEqual([true, true, false]);
  });
});
