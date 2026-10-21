import { fmtClock, statusAt, weatherAt, type Replay } from "@/lib/replay";
import { tempUnit, tempValue, windUnit, windValue, type Units } from "@/lib/units";

export function StatusStrip({
  replay,
  t,
  kind,
  lap,
  totalLaps,
  clock,
  units,
}: {
  replay: Replay;
  t: number;
  kind: "race" | "quali";
  lap: number;
  totalLaps: number;
  clock: number;
  units: Units;
}) {
  const status = statusAt(replay.file, t);
  const w = weatherAt(replay.file.weather, t);
  const tone = !status ? "" : status.code === "1" ? "" : status.code === "2" ? "rp-pill-yellow" : status.code === "5" ? "rp-pill-red" : "rp-pill-sc";
  const num = (v: number | null | undefined, unit: string, d = 1) => (v == null ? "-" : `${v.toFixed(d)}${unit}`);
  return (
    <div className="rp-top" role="group" aria-label="Session status">
      {kind === "race" && (
        <div className="rp-stat">
          <span className="rp-big num">{lap}<small>/{totalLaps}</small></span>
          <span className="rp-label">Lap</span>
        </div>
      )}
      <div className="rp-stat">
        <span className="rp-big num">{fmtClock(clock)}</span>
        <span className="rp-label">{kind === "race" ? "Race time" : "Session time"}</span>
      </div>
      {status && (
        <div className="rp-stat">
          <span className={`rp-pill ${tone}`}>{status.label}</span>
          <span className="rp-label">Track</span>
        </div>
      )}
      {w && (
        <dl className="rp-weather" aria-label="Weather">
          <div><dt>Track</dt><dd className="num">{num(w.track == null ? w.track : tempValue(w.track, units), tempUnit(units))}</dd></div>
          <div><dt>Air</dt><dd className="num">{num(w.air == null ? w.air : tempValue(w.air, units), tempUnit(units))}</dd></div>
          <div><dt>Humidity</dt><dd className="num">{num(w.humidity, "%", 0)}</dd></div>
          <div><dt>Wind</dt><dd className="num">{num(w.wind == null ? w.wind : windValue(w.wind, units), windUnit(units))}</dd></div>
          <div><dt>Rain</dt><dd>{w.rain ? "Yes" : "No"}</dd></div>
        </dl>
      )}
    </div>
  );
}
