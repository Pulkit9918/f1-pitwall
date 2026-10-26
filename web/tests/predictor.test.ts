import { describe, expect, it } from "vitest";
import { byMargin, byRegime, overall, pct, places, sessionsWithStops, signedPlaces, stopRows, verdict, type ScoreRow, type StopsDoc } from "../lib/predictor";

const row = (o: Partial<ScoreRow>): ScoreRow => ({
  scope: "all", regime: "all", margin: "all", stops: 100, hit: 0.5, within_one: 0.8, mae: 0.8, bias: 0.1, in_range: 0.7,
  no_loss_hit: 0.2, no_loss_mae: 2, global_hit: 0.45, global_mae: 0.9, reliable: true, ...o,
});

describe("score rows", () => {
  const rows = [
    row({}), row({ scope: "undisturbed", stops: 40 }),
    row({ regime: "sc" }), row({ regime: "green" }), row({ regime: "vsc" }), row({ scope: "undisturbed", regime: "green" }),
    row({ margin: "over 3 s" }), row({ margin: "under 1 s" }), row({ margin: "no margin" }), row({ margin: "1 to 3 s" }),
  ];
  it("picks the overall row of a scope", () => {
    expect(overall(rows, "all")?.stops).toBe(100);
    expect(overall(rows, "undisturbed")?.stops).toBe(40);
    expect(overall([], "all")).toBeUndefined();
  });
  it("lists regimes in a fixed order and margins from tight to loose, for one scope", () => {
    expect(byRegime(rows, "all").map((r) => r.regime)).toEqual(["green", "sc", "vsc"]);
    expect(byRegime(rows, "undisturbed").map((r) => r.regime)).toEqual(["green"]);
    expect(byMargin(rows, "all").map((r) => r.margin)).toEqual(["under 1 s", "1 to 3 s", "over 3 s", "no margin"]);
  });
  it("formats shares and errors, with a dash for no value", () => {
    expect([pct(0.4567), pct(0.4567, 1), pct(null), places(0.8333), places(undefined), signedPlaces(0.12), signedPlaces(-0.5), signedPlaces(0)]).toEqual(["46%", "45.7%", "-", "0.83", "-", "+0.12", "-0.50", "0.00"]);
  });
});

describe("stops", () => {
  const doc: StopsDoc = {
    schema: 1, sessions: [{ key: "a", year: 2025, round: 1, event: "X" }, { key: "b", year: 2025, round: 2, event: "Y" }],
    s: [0, 0, 1], d: ["AAA", "BBB", "CCC"], l: [10, 20, 5], r: ["g", "s", "g"], n: [3, 2, 1], p: [5, 3, 2], f: [4, 3, 2], w: [6, 4, 2], a: [5, 6, 3], m: [0.7, null, 1], o: [0, 2, 0],
  };
  it("returns the stops of one session as rows", () => {
    const rows = stopRows(doc, 0);
    expect(rows).toHaveLength(2);
    expect(rows[1]).toMatchObject({ driver: "BBB", lap: 20, regime: "s", before: 2, predicted: 3, fast: 3, slow: 4, actual: 6, margin: null, disturbed: true });
    expect(rows[0].disturbed).toBe(false);
  });
  it("says whether the outcome was exact, inside the model's range or outside it", () => {
    const [a, b] = stopRows(doc, 0);
    expect([verdict(a), verdict(b)]).toEqual(["exact", "outside"]);
    expect(verdict({ ...a, actual: 6 })).toBe("in range");
    expect(verdict(stopRows(doc, 1)[0])).toBe("outside");
  });
  it("counts stops per session", () => {
    expect(sessionsWithStops(doc)).toEqual([{ index: 0, count: 2 }, { index: 1, count: 1 }]);
  });
});
