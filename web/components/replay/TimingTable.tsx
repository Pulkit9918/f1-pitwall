import { CompoundChip } from "@/components/CompoundChip";
import { fmtLap } from "@/lib/format";
import { tyreAt, type Cell, type LapIndex, type TimingRow } from "@/lib/replay";

export type GapCell = { gap: string; interval: string; close: boolean };

function C({ cell, sector = false }: { cell: Cell; sector?: boolean }) {
  const text = cell.v == null ? "-" : sector ? cell.v.toFixed(3) : fmtLap(cell.v);
  const cls = cell.purple ? "rp-purple" : cell.green ? "rp-green" : "";
  const why = cell.purple ? "Best of the session so far" : cell.green ? "Driver's own best so far" : undefined;
  return (
    <td className={`num ${cls}`} title={why}>
      {text}
      {why && <span className="sr-only"> ({why})</span>}
    </td>
  );
}

export function TimingTable({ rows, idx, t, positions, gaps }: { rows: TimingRow[]; idx: LapIndex; t: number; positions: Map<string, number>; gaps?: Map<string, GapCell> }) {
  return (
    <>
      <div className="table-wrap">
        <table className="rp-timing">
          <thead>
            <tr>
              <th className="num">Pos</th><th>Driver</th>{gaps && <><th className="num">Gap</th><th className="num">Int</th></>}<th className="num">Laps</th><th className="num">Last lap</th>
              <th className="num">Best lap</th><th className="num">S1</th><th className="num">S2</th><th className="num">S3</th><th>Tyre</th><th className="num">Stops</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const tyre = tyreAt(idx.get(r.code) ?? [], t);
              const g = gaps?.get(r.code);
              return (
                <tr key={r.code}>
                  <td className="num">{positions.get(r.code) ?? ""}</td>
                  <td><strong>{r.code}</strong></td>
                  {gaps && (
                    <>
                      <td className="num">{g?.gap ?? ""}</td>
                      <td className={`num${g?.close ? " rp-close" : ""}`}>{g?.interval ?? ""}</td>
                    </>
                  )}
                  <td className="num">{r.laps}</td>
                  <C cell={r.last} />
                  <C cell={r.best} />
                  <C cell={r.sectors[0]} sector />
                  <C cell={r.sectors[1]} sector />
                  <C cell={r.sectors[2]} sector />
                  <td><span className="rp-tyre"><CompoundChip compound={tyre.compound} /><span className="num rp-age">{tyre.life ?? ""}</span></span></td>
                  <td className="num">{tyre.stops}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="axis-caption">
        Times are those of each driver's last completed lap. Purple marks the best of the session so far, green a driver's own best.
        Laps deleted by the stewards are left out.
      </p>
    </>
  );
}
