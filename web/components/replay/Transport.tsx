"use client";

import { SPEEDS } from "@/lib/usePlayback";
import { fmtClock, type TimeBand } from "@/lib/replay";

const SKIPS = [
  { label: "-1m", dt: -60 }, { label: "-30s", dt: -30 }, { label: "-5s", dt: -5 },
  { label: "+5s", dt: 5 }, { label: "+30s", dt: 30 }, { label: "+1m", dt: 60 },
];

export function Transport({
  start,
  end,
  t,
  clock0,
  playing,
  speed,
  bands,
  ticks,
  onToggle,
  onSeek,
  onSkip,
  onSpeed,
}: {
  start: number;
  end: number;
  t: number;
  clock0: number;
  playing: boolean;
  speed: number;
  bands: TimeBand[];
  ticks: { t: number; label: string }[];
  onToggle: () => void;
  onSeek: (t: number) => void;
  onSkip: (dt: number) => void;
  onSpeed: (s: number) => void;
}) {
  const span = Math.max(1, end - start);
  const pct = (x: number) => `${Math.max(0, Math.min(100, ((x - start) / span) * 100))}%`;
  return (
    <div className="rp-transport">
      <div className="rp-controls">
        <button type="button" className="rp-play" onClick={onToggle} aria-label={playing ? "Pause" : "Play"}>
          {playing ? (
            <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><rect x="6" y="5" width="4" height="14" /><rect x="14" y="5" width="4" height="14" /></svg>
          ) : (
            <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path d="M7 4.5v15l12-7.5z" /></svg>
          )}
        </button>
        <div className="rp-skips" role="group" aria-label="Skip">
          {SKIPS.map((s) => (
            <button key={s.label} type="button" className="rp-skip" onClick={() => onSkip(s.dt)}>{s.label}</button>
          ))}
        </div>
        <div className="rp-speeds" role="group" aria-label="Playback speed">
          {SPEEDS.map((s) => (
            <button key={s} type="button" className={`rp-speed-btn${s === speed ? " on" : ""}`} aria-pressed={s === speed} onClick={() => onSpeed(s)}>{s}x</button>
          ))}
        </div>
        <span className="rp-clock num">{fmtClock(t - clock0)}</span>
      </div>
      <div className="rp-scrub">
        <div className="rp-scrub-bands" aria-hidden="true">
          {bands.map((b, i) => (
            <span key={i} className={`rp-band rp-band-${b.kind.toLowerCase()}`} style={{ left: pct(b.t0), width: `max(2px, calc(${pct(b.t1)} - ${pct(b.t0)}))` }} />
          ))}
          <span className="rp-scrub-fill" style={{ width: pct(t) }} />
        </div>
        <input
          type="range"
          min={start}
          max={end}
          step={1}
          value={t}
          onChange={(e) => onSeek(Number(e.target.value))}
          aria-label="Position in the session"
          aria-valuetext={fmtClock(t - clock0)}
        />
        <div className="rp-ticks" aria-hidden="true">
          {ticks.map((k) => (
            <span key={k.label} style={{ left: pct(k.t) }}>{k.label}</span>
          ))}
        </div>
      </div>
      <ul className="legend rp-legend" aria-label="Timeline markers">
        <li><span className="swatch rp-band-yellow" /> Yellow flag</li>
        <li><span className="swatch band-sc" /> Safety car</li>
        <li><span className="swatch band-vsc" /> Virtual safety car</li>
        <li><span className="swatch band-red" /> Red flag</li>
      </ul>
    </div>
  );
}
