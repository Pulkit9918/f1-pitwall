import { DRIVER_COLORS } from "@/lib/colors";
import { channelAt, drsOpen, type BoardRow, type Replay } from "@/lib/replay";

export function TelemetryCards({
  replay,
  t,
  rows,
  kind,
  slots,
}: {
  replay: Replay;
  t: number;
  rows: BoardRow[];
  kind: "race" | "quali";
  slots: (string | null)[];
}) {
  const picked = slots.flatMap((code, slot) => (code ? [{ code, slot }] : []));
  if (picked.length === 0) return <p className="muted">Select up to three drivers in the list to see their speed, gear, throttle and brake.</p>;
  return (
    <div className="rp-cards">
      {picked.map(({ code, slot }) => {
        const ch = channelAt(replay, code, t);
        const i = rows.findIndex((r) => r.code === code);
        const ahead = kind === "race" && i > 0 ? rows[i - 1] : null;
        const behind = kind === "race" && i >= 0 && i < rows.length - 1 ? rows[i + 1] : null;
        return (
          <div key={code} className="rp-card" style={{ borderTopColor: DRIVER_COLORS[slot] }}>
            <div className="rp-card-head">
              <strong>{code}</strong>
              <span className="muted small">{replay.teams[code]?.name ?? ""}</span>
              <span className="muted">{i >= 0 ? `P${rows[i].pos}` : ""}</span>
            </div>
            {ch ? (
              <>
                <div className="rp-speed">
                  <span className="num">{ch.speed}</span> <small>km/h</small>
                </div>
                <dl className="rp-kv">
                  <div><dt>Gear</dt><dd className="num">{ch.gear || "N"}</dd></div>
                  <div><dt>DRS</dt><dd title={`code ${ch.drs}`}>{drsOpen(ch.drs) ? "Open" : "Closed"}</dd></div>
                </dl>
                <div className="rp-meter">
                  <span>Throttle</span>
                  <span className="rp-meter-track"><span style={{ width: `${ch.throttle}%` }} /></span>
                  <span className="num">{ch.throttle}%</span>
                </div>
                <div className="rp-meter">
                  <span>Brake</span>
                  <span className="rp-meter-track"><span style={{ width: ch.brake ? "100%" : "0%" }} /></span>
                  <span className="num">{ch.brake ? "On" : "Off"}</span>
                </div>
              </>
            ) : (
              <p className="muted small">No car data at this moment.</p>
            )}
            {kind === "race" && (
              <p className="rp-near small">
                {ahead ? `Ahead ${ahead.code} ${rows[i].interval}` : "Leading"}
                <br />
                {behind ? `Behind ${behind.code} ${behind.interval}` : "Last"}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}

