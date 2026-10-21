"use client";

import { useState } from "react";
import { battleRows, battleSummary, type AnalysisDoc } from "@/lib/analysis";

export function BattleTable({ analysis }: { analysis: AnalysisDoc }) {
  const [all, setAll] = useState(false);
  const rows = battleRows(analysis, all);
  const sum = battleSummary(rows);
  const hidden = analysis.battles.length - battleRows(analysis, false).length;
  if (analysis.battles.length === 0) return <p className="muted">No pit stops in this session were made with a rival within 3 seconds.</p>;
  return (
    <>
      <p className="muted small">
        Stops made with a rival within 3 seconds the lap before, and who was ahead once both had stopped. An undercut is the car behind stopping first;
        an overcut is the car behind staying out longer. Order changes around the stops are detected, not proven to be caused by them.
      </p>
      <div className="filters">
        <div role="group" aria-label="Which stops" className="chips">
          <button type="button" className={`chip${!all ? " chip-on" : ""}`} aria-pressed={!all} onClick={() => setAll(false)}>Green-flag stops</button>
          <button type="button" className={`chip${all ? " chip-on" : ""}`} aria-pressed={all} onClick={() => setAll(true)}>Include safety car and VSC{hidden ? ` (${hidden})` : ""}</button>
        </div>
      </div>
      <p className="small">
        Undercuts that worked: <strong>{sum.undercut[0]} of {sum.undercut[1]}</strong>. Overcuts that worked: <strong>{sum.overcut[0]} of {sum.overcut[1]}</strong>.
      </p>
      {rows.length === 0 ? <p className="muted">No green-flag stop pairs in this session.</p> : (
        <div className="table-wrap">
          <table className="narrow">
            <thead>
              <tr><th>Move</th><th>Attacker</th><th>Defender</th><th className="num">Gap before</th><th className="num">Stops on laps</th><th>Result</th><th className="num">Margin</th></tr>
            </thead>
            <tbody>
              {rows.map((b, i) => (
                <tr key={`${b.attacker}-${b.defender}-${b.first_lap}-${i}`}>
                  <td>{b.kind === "undercut" ? "Undercut" : "Overcut"}{b.neutralised ? " (safety car or VSC)" : ""}</td>
                  <td>{b.attacker}</td>
                  <td>{b.defender}</td>
                  <td className="num">{b.gap_before_s !== null ? `${b.gap_before_s.toFixed(1)} s` : "–"}</td>
                  <td className="num">{b.first_lap} and {b.second_lap}</td>
                  <td>{b.attacker_ahead ? "Attacker ahead" : "Still behind"}</td>
                  <td className="num">{b.margin_after_s !== null ? `${b.margin_after_s > 0 ? "+" : "−"}${Math.abs(b.margin_after_s).toFixed(1)} s` : "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
