import { CompoundChip } from "@/components/CompoundChip";
import { DRIVER_COLORS } from "@/lib/colors";
import { fmtLap } from "@/lib/format";
import { lapHistory, type LapIndex } from "@/lib/replay";

export function LapHistory({ idx, slots, t }: { idx: LapIndex; slots: (string | null)[]; t: number }) {
  const picked = slots.flatMap((code, slot) => (code ? [{ code, slot }] : []));
  if (picked.length === 0) return <p className="muted">Select up to three drivers in the list to see their laps, one row per lap.</p>;
  const h = lapHistory(idx, picked.map((p) => p.code), t);
  if (h.laps.length === 0) return <p className="muted">No laps completed yet.</p>;
  return (
    <>
      <div className="table-wrap">
        <table className="rp-timing">
          <thead>
            <tr>
              <th className="num">Lap</th>
              {picked.map(({ code, slot }) => (
                <th key={code} style={{ borderBottom: `3px solid ${DRIVER_COLORS[slot]}` }}>{code}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {h.laps.map((lap) => (
              <tr key={lap}>
                <td className="num">{lap}</td>
                {picked.map(({ code }) => {
                  const rec = h.rows.get(lap)?.get(code);
                  if (!rec) return <td key={code} className="muted">-</td>;
                  const cls = !rec.deleted && rec.time === h.sessionBest ? "rp-purple" : !rec.deleted && rec.time === h.own.get(code) ? "rp-green" : "";
                  const pit = rec.pitIn != null ? "in" : rec.pitOut != null ? "out" : "";
                  return (
                    <td key={code} className={`num ${cls}`}>
                      <span className="rp-lapcell">
                        <span style={rec.deleted ? { textDecoration: "line-through" } : undefined}>{fmtLap(rec.time)}</span>
                        <CompoundChip compound={rec.compound} />
                        <small className="muted">{pit ? `pit ${pit}` : ""}</small>
                      </span>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="axis-caption">Newest lap first. Purple is the best lap of the session so far, green the driver&apos;s own best. A struck-out time was deleted by the stewards.</p>
    </>
  );
}
