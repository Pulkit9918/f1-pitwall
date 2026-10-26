import { SECTOR_COLOR } from "@/lib/colors";
import type { SectorColour } from "@/lib/laps";

const NAME: Record<SectorColour, string> = { purple: "session best at the time", green: "personal best at the time", yellow: "slower than the driver's best", none: "" };

// A sector time with a coloured bar beside it. The time stays in text colour; the bar and its title carry the colour.
export function SectorTime({ value, colour }: { value: number | null; colour: SectorColour }) {
  if (value == null) return <span className="muted">-</span>;
  return (
    <span className="sector-time" title={NAME[colour] || undefined}>
      <span className="sector-bar" style={{ background: SECTOR_COLOR[colour] }} aria-hidden="true" />
      <span className="num">{value.toFixed(3)}</span>
      {colour !== "none" && <span className="sr-only">{NAME[colour]}</span>}
    </span>
  );
}
