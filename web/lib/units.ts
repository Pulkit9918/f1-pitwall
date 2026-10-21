// Metric and imperial display. The data stays metric; these only convert what is drawn.
export type Units = "metric" | "imperial";

export const kmhToMph = (v: number) => v * 0.621371;
export const cToF = (v: number) => v * 1.8 + 32;
export const msToMph = (v: number) => v * 2.23694;

export const speedUnit = (u: Units) => (u === "imperial" ? "mph" : "km/h");
export const tempUnit = (u: Units) => (u === "imperial" ? "°F" : "°C");
export const windUnit = (u: Units) => (u === "imperial" ? " mph" : " m/s");

export function speedValue(kmh: number, u: Units): number {
  return Math.round(u === "imperial" ? kmhToMph(kmh) : kmh);
}
export function tempValue(c: number, u: Units): number {
  return u === "imperial" ? cToF(c) : c;
}
export function windValue(ms: number, u: Units): number {
  return u === "imperial" ? msToMph(ms) : ms;
}

const KEY = "pitwall-units";
export function loadUnits(): Units {
  try {
    return window.localStorage.getItem(KEY) === "imperial" ? "imperial" : "metric";
  } catch {
    return "metric";
  }
}
export function saveUnits(u: Units): void {
  try {
    window.localStorage.setItem(KEY, u);
  } catch {
    /* storage can be blocked; the choice then lasts only for this page */
  }
}
