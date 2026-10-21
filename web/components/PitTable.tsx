import { fmtSeconds } from "@/lib/format";
import type { PitStop } from "@/lib/types";
import { CompoundChip } from "./CompoundChip";

export function PitTable({ stops }: { stops: PitStop[] }) {
  if (stops.length === 0) return <p className="muted">No pit stops were recorded for this session.</p>;
  return (
    <div className="table-wrap">
      <table className="narrow">
        <thead>
          <tr>
            <th className="num">In lap</th><th>Driver</th><th>Tyres</th>
            <th className="num">Time in pit lane</th><th>Under green flag</th><th className="num">Position before</th>
          </tr>
        </thead>
        <tbody>
          {stops.map((s, i) => (
            <tr key={`${s.driver}-${s.lap}-${i}`}>
              <td className="num">{s.lap}</td>
              <td>{s.driver}</td>
              <td><span className="tyre-change"><CompoundChip compound={s.before} /> to <CompoundChip compound={s.after} /></span></td>
              <td className="num">{fmtSeconds(s.pitLane)}</td>
              <td>{s.green ? "Yes" : "No"}</td>
              <td className="num">{s.positionBefore ?? "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
