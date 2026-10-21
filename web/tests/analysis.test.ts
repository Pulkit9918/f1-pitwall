import { describe, expect, it } from "vitest";
import { predictionAt, battleRows, battleSummary, confidenceNote, gapSeries, pitNowAt, pitNowSeries, regimeAt, type AnalysisDoc, type Battle } from "../lib/analysis";

function doc(): AnalysisDoc {
  const n = null;
  return {
    schema: 1, session_key: "2099-R01-R", laps: 4, drivers: ["AAA", "BBB"],
    series: {
      AAA: { pos: [1, 1, 1, 1], leader: [0, 0, 0, 0], interval: [n, n, n, n], loss: [22, 22, 12.5, n], pred: [2, 2, 1, n], fast: [2, 1, 1, n], slow: [3, 2, 2, n], margin: [4, 2, 0.5, n], regime: "ggsr" },
      BBB: { pos: [2, 2, n, 2], leader: [1.2, 3, n, 5.1], interval: [1.2, 3, n, 5.1], loss: [22, 22, n, n], pred: [3, 3, n, n], fast: [3, 3, n, n], slow: [3, 3, n, n], margin: [1, 1, n, n], regime: "gg.g" },
    },
    stops: [{ driver: "BBB", lap: 2 }],
    battles: [],
    loss_ratio: { green: { stops: 4000, median_loss_s: 22.7, p25_loss_s: 20.8, p75_loss_s: 25.1, ratio: 1, reliable: true }, sc: { stops: 136, median_loss_s: 17, p25_loss_s: 1.8, p75_loss_s: 38.4, ratio: 0.75, reliable: true } },
  };
}
const battle = (o: Partial<Battle>): Battle => ({ kind: "undercut", attacker: "A", defender: "B", first_by: "A", first_lap: 10, second_lap: 13, gap_before_s: 1.5, attacker_ahead: true, margin_after_s: 2, neutralised: false, ...o });

describe("race analysis helpers", () => {
  it("reads the regime letter for a lap, and unknown outside the data", () => {
    expect(regimeAt(doc().series.AAA, 3)).toBe("sc");
    expect(regimeAt(doc().series.AAA, 4)).toBe("red");
    expect(regimeAt(doc().series.BBB, 3)).toBe("unknown");
    expect(regimeAt(doc().series.AAA, 99)).toBe("unknown");
  });
  it("skips laps with no gap when building a series", () => {
    expect(gapSeries(doc(), "BBB", "leader")).toEqual([{ lap: 1, value: 1.2 }, { lap: 2, value: 3 }, { lap: 4, value: 5.1 }]);
    expect(gapSeries(doc(), "ZZZ", "leader")).toEqual([]);
  });
  it("finds the real stop on the next lap and the position after the out-lap", () => {
    const p = pitNowAt(doc(), "BBB", 1)!;
    expect(p.stopsNextLap).toBe(true);
    expect(p.actualAfter).toBeNull();           // lap 3 has no position for BBB in this data
    expect(p.predicted).toBe(3);
    const q = pitNowAt(doc(), "AAA", 2)!;
    expect(q.stopsNextLap).toBe(false);
    expect(q.actualAfter).toBeNull();
    expect(pitNowAt(doc(), "AAA", 9)).toBeNull();
  });
  it("gives the actual position when it exists", () => {
    const d = doc(); d.stops = [{ driver: "AAA", lap: 2 }];
    expect(pitNowAt(d, "AAA", 1)!.actualAfter).toBe(1);
  });
  it("builds the prediction lines without the empty laps", () => {
    const s = pitNowSeries(doc(), "AAA");
    expect(s.predicted).toEqual([{ lap: 1, value: 2 }, { lap: 2, value: 2 }, { lap: 3, value: 1 }]);
    expect(s.now).toHaveLength(4);
  });
  it("hides safety car stops unless asked, and sorts by lap", () => {
    const d = doc();
    d.battles = [battle({ first_lap: 20 }), battle({ first_lap: 5, neutralised: true }), battle({ first_lap: 12 })];
    expect(battleRows(d, false).map((b) => b.first_lap)).toEqual([12, 20]);
    expect(battleRows(d, true).map((b) => b.first_lap)).toEqual([5, 12, 20]);
  });
  it("tallies how many attempts worked for each move", () => {
    const rows = [battle({}), battle({ attacker_ahead: false }), battle({ kind: "overcut", attacker_ahead: false })];
    expect(battleSummary(rows)).toEqual({ undercut: [1, 2], overcut: [0, 1] });
  });
  it("cautions under a safety car with the real spread, says nothing for green, and refuses for red", () => {
    const r = doc().loss_ratio;
    expect(confidenceNote("green", r)).toBeNull();
    expect(confidenceNote("sc", r)).toMatch(/Low confidence.*median 17 seconds \(green flag: 22\.7\).*1\.8 to 38\.4 seconds/);
    expect(confidenceNote("vsc", r)).toMatch(/partly green/);
    expect(confidenceNote("red", r)).toMatch(/No prediction/);
  });
  it("reads the prediction made at the end of the lap a driver has just finished", () => {
    const d = doc();
    expect(predictionAt(d, "AAA", 2)).toEqual({ position: 2, regime: "green" });
    expect(predictionAt(d, "AAA", 3)).toEqual({ position: 1, regime: "sc" });
    expect(predictionAt(d, "AAA", 4)).toEqual({ position: null, regime: "red" });
    expect(predictionAt(d, "AAA", 0)).toBeNull();      // no lap finished yet
    expect(predictionAt(d, "AAA", 9)).toBeNull();
    expect(predictionAt(d, "ZZZ", 1)).toBeNull();
    expect(predictionAt(null, "AAA", 1)).toBeNull();
  });
});
