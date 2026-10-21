import { describe, expect, it } from "vitest";
import { cToF, kmhToMph, loadUnits, msToMph, saveUnits, speedUnit, speedValue, tempUnit, tempValue, windUnit, windValue } from "../lib/units";

describe("units", () => {
  it("converts speed, temperature and wind", () => {
    expect(kmhToMph(100)).toBeCloseTo(62.1371, 3);
    expect(cToF(0)).toBe(32);
    expect(cToF(100)).toBe(212);
    expect(msToMph(10)).toBeCloseTo(22.3694, 3);
  });
  it("leaves metric values alone and rounds speeds", () => {
    expect(speedValue(250, "metric")).toBe(250);
    expect(speedValue(250, "imperial")).toBe(155);
    expect(tempValue(25, "metric")).toBe(25);
    expect(tempValue(25, "imperial")).toBeCloseTo(77);
    expect(windValue(2, "metric")).toBe(2);
    expect(windValue(2, "imperial")).toBeCloseTo(4.47, 2);
  });
  it("names the unit for each system", () => {
    expect([speedUnit("metric"), speedUnit("imperial")]).toEqual(["km/h", "mph"]);
    expect([tempUnit("metric"), tempUnit("imperial")]).toEqual(["°C", "°F"]);
    expect([windUnit("metric"), windUnit("imperial")]).toEqual([" m/s", " mph"]);
  });
  it("falls back to metric when storage is not there or throws", () => {
    expect(loadUnits()).toBe("metric");   // no window in this environment
    expect(() => saveUnits("imperial")).not.toThrow();
  });
});
