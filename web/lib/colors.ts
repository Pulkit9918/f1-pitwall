// Tyre compound colours are the broadcast colours, and they carry meaning, so nothing else on the site uses them
// as decoration. The driver-line colours are validated for colour-blind separation on the page background.

export const COMPOUND_COLOR: Record<string, string> = {
  SOFT: "#e8423f",
  MEDIUM: "#f2c230",
  HARD: "#e9e9e6",
  INTERMEDIATE: "#43b05c",
  WET: "#3d7de0",
};
export const COMPOUND_UNKNOWN = "#7a8294";

export const COMPOUND_LETTER: Record<string, string> = {
  SOFT: "S",
  MEDIUM: "M",
  HARD: "H",
  INTERMEDIATE: "I",
  WET: "W",
};

export function compoundColor(c: string | null | undefined): string {
  return (c && COMPOUND_COLOR[c.toUpperCase()]) || COMPOUND_UNKNOWN;
}

export function compoundLetter(c: string | null | undefined): string {
  return (c && COMPOUND_LETTER[c.toUpperCase()]) || "?";
}

// Dark text on the light compounds, light text on the dark ones.
export function onCompound(c: string | null | undefined): string {
  const k = (c || "").toUpperCase();
  return k === "SOFT" || k === "WET" ? "#ffffff" : "#14171f";
}

const PAGE_GROUND = "#0f1218";

function channels(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function luminance([r, g, b]: [number, number, number]): number {
  const f = (v: number) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}

export function contrastWith(hex: string, other: string = PAGE_GROUND): number {
  const a = luminance(channels(hex));
  const b = luminance(channels(other));
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

export function teamFill(hex: string | null | undefined): string | null {
  if (!hex || !/^#[0-9a-fA-F]{6}$/.test(hex)) return null;
  let c = channels(hex);
  for (let i = 0; i < 20 && contrastWith(rgb(c)) < 3; i++) c = c.map((v) => Math.round(v + (255 - v) * 0.12)) as [number, number, number];
  return rgb(c);
}

function rgb([r, g, b]: [number, number, number]): string {
  return `#${[r, g, b].map((v) => v.toString(16).padStart(2, "0")).join("")}`;
}

export const DRIVER_COLORS = ["#3987e5", "#d95926", "#199e70"];
export const MAX_COMPARED = DRIVER_COLORS.length;
