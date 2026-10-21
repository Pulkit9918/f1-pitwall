import { COMPOUND_COLOR } from "@/lib/colors";
import { fmtDeg } from "@/lib/format";
import type { Circuit, DegradationRow } from "@/lib/types";

const COMPOUNDS = ["SOFT", "MEDIUM", "HARD"] as const;

// For each circuit and compound, the layout with the most stints.
function pick(c: Circuit, compound: string, reliableOnly: boolean): DegradationRow | null {
  const rows = c.degradation.filter((d) => d.compound.toUpperCase() === compound && d.median_degradation_s_per_lap != null && (!reliableOnly || d.is_reliable));
  return rows.sort((a, b) => b.stints - a.stints)[0] ?? null;
}

export function DegradationMatrix({ circuits, reliableOnly }: { circuits: Circuit[]; reliableOnly: boolean }) {
  const rows = circuits
    .map((c) => ({ c, cells: COMPOUNDS.map((k) => pick(c, k, reliableOnly)) }))
    .filter((r) => r.cells.some(Boolean))
    .sort((a, b) => a.c.circuit_name.localeCompare(b.c.circuit_name));
  if (rows.length === 0) return <p className="muted">No circuit has enough stints on a compound to show.</p>;
  const max = Math.max(0.001, ...rows.flatMap((r) => r.cells.map((d) => Math.max(0, d?.median_degradation_s_per_lap ?? 0))));

  return (
    <div className="table-wrap">
      <table className="matrix">
        <thead>
          <tr>
            <th>Circuit</th>
            {COMPOUNDS.map((k) => <th key={k}>{k.charAt(0) + k.slice(1).toLowerCase()}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map(({ c, cells }) => (
            <tr key={c.circuit_id}>
              <td>{c.circuit_name}</td>
              {cells.map((d, i) => (
                <td key={COMPOUNDS[i]}>
                  {d && d.median_degradation_s_per_lap != null ? (
                    <div className="cell" title={`${d.stints} stints in ${d.races} races, ${d.is_reliable ? "enough data" : "too few for a reliable figure"}`}>
                      <span className="cell-text">{fmtDeg(d.median_degradation_s_per_lap)}</span>
                      <span className="cell-track">
                        <span className="cell-bar" style={{ width: `${(Math.max(0, d.median_degradation_s_per_lap) / max) * 100}%`, background: COMPOUND_COLOR[COMPOUNDS[i]], opacity: d.is_reliable ? 1 : 0.45 }} />
                      </span>
                    </div>
                  ) : (
                    <span className="muted">-</span>
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
