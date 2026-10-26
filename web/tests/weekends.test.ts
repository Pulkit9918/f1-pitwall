import { describe, expect, it } from "vitest";
import { groupWeekends, pickYear, type WeekendSession } from "../lib/weekends";

const s = (year: number, round: number, code: string, event = `Event ${round}`): WeekendSession => ({
  key: `${year}-R${String(round).padStart(2, "0")}-${code}`, year, round, session_code: code, event,
});

describe("groupWeekends", () => {
  it("puts the newest year first and the rounds in order", () => {
    const g = groupWeekends([s(2024, 2, "R"), s(2025, 1, "R"), s(2024, 1, "R"), s(2025, 3, "R")]);
    expect(g.map((y) => y.year)).toEqual([2025, 2024]);
    expect(g[0].weekends.map((w) => w.round)).toEqual([1, 3]);
    expect(g[1].weekends.map((w) => w.round)).toEqual([1, 2]);
  });

  it("puts a weekend's sessions in the order they run", () => {
    const g = groupWeekends([s(2025, 2, "R"), s(2025, 2, "Q"), s(2025, 2, "S"), s(2025, 2, "SQ"), s(2025, 2, "FP1")]);
    expect(g[0].weekends[0].sessions.map((x) => x.code)).toEqual(["FP1", "SQ", "S", "Q", "R"]);
    expect(g[0].weekends[0].sessions.map((x) => x.label)).toEqual(["Practice 1", "Sprint qualifying", "Sprint", "Qualifying", "Race"]);
  });

  it("keeps one row per weekend however many sessions it has", () => {
    const g = groupWeekends([s(2025, 2, "Q"), s(2025, 2, "R"), s(2025, 3, "R")]);
    expect(g[0].weekends).toHaveLength(2);
    expect(g[0].weekends[0].sessions).toHaveLength(2);
  });

  it("can keep only some session codes, and drops weekends left empty", () => {
    const g = groupWeekends([s(2025, 1, "FP1"), s(2025, 1, "R"), s(2025, 2, "R")], ["FP1", "FP2", "FP3"]);
    expect(g[0].weekends).toHaveLength(1);
    expect(g[0].weekends[0].sessions.map((x) => x.code)).toEqual(["FP1"]);
  });

  it("uses the session's own name when it has one, and shows an unknown code as it is", () => {
    const g = groupWeekends([{ ...s(2025, 1, "R"), name: "Grand Prix" }, s(2025, 1, "XX")]);
    expect(g[0].weekends[0].sessions.map((x) => x.label)).toEqual(["Grand Prix", "XX"]);
  });

  it("gives nothing for nothing", () => {
    expect(groupWeekends([])).toEqual([]);
  });
});

describe("pickYear", () => {
  const g = groupWeekends([s(2024, 1, "R"), s(2025, 1, "R")]);
  it("takes the wanted year when it exists", () => expect(pickYear(g, "2024")).toBe(2024));
  it("falls back to the newest year", () => {
    expect(pickYear(g, null)).toBe(2025);
    expect(pickYear(g, "1999")).toBe(2025);
    expect(pickYear(g, "abc")).toBe(2025);
  });
  it("is null with no sessions", () => expect(pickYear([], "2024")).toBeNull());
});
