import { describe, expect, it } from "vitest";
import { biggestMovers, gainedLabel, lastName, podiumNames, seriesPoints, type RaceResult, type SeasonRace } from "../lib/seasons";

const r = (o: Partial<RaceResult>): RaceResult => ({
  position: null, driver_id: "x", code: "XXX", name: "A B", constructor_id: null, team: null, grid: null, points: 0, laps: null, status: null,
  classified: true, gained: null, fastest: false, ...o,
});
const race = (results: RaceResult[]): SeasonRace => ({ round: 1, name: "GP", date: null, circuit_id: null, podium: [], results });

describe("season helpers", () => {
  it("labels places gained with a sign and a dash for unknown", () => {
    expect(gainedLabel(3)).toBe("+3");
    expect(gainedLabel(-2)).toBe("−2");
    expect(gainedLabel(0)).toBe("0");
    expect(gainedLabel(null)).toBe("–");
  });
  it("takes the last word as the surname", () => {
    expect(lastName("Max Verstappen")).toBe("Verstappen");
    expect(lastName("Madonna")).toBe("Madonna");
  });
  it("lists the podium in finishing order whatever the row order", () => {
    const rc = race([r({ position: 2, name: "B Two" }), r({ position: 1, name: "A One" }), r({ position: 3, name: "C Three" }), r({ position: 4, name: "D Four" })]);
    expect(podiumNames(rc)).toEqual(["One", "Two", "Three"]);
  });
  it("finds the biggest gainer and loser among classified drivers only", () => {
    const rc = race([
      r({ driver_id: "a", position: 1, gained: 1 }),
      r({ driver_id: "b", position: 2, gained: 6 }),
      r({ driver_id: "c", position: 9, gained: -4 }),
      r({ driver_id: "d", position: 15, gained: -9, classified: false }),
      r({ driver_id: "e", position: null, gained: null }),
    ]);
    expect(biggestMovers(rc).gain?.driver_id).toBe("b");
    expect(biggestMovers(rc).loss?.driver_id).toBe("c");
    expect(biggestMovers(race([r({ gained: 0 })]))).toEqual({ gain: null, loss: null });
  });
  it("skips rounds with no value and keeps the round number", () => {
    expect(seriesPoints([1, 2, 3], [null, 5, 9])).toEqual([{ round: 2, value: 5 }, { round: 3, value: 9 }]);
  });
});
