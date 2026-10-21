"use client";

import { useState } from "react";
import { DegradationMatrix } from "@/components/DegradationMatrix";
import { PitLossChart } from "@/components/PitLossChart";
import { Ready } from "@/components/State";
import { useCircuits } from "@/lib/data";

export default function CircuitsPage() {
  const load = useCircuits();
  const [reliableOnly, setReliableOnly] = useState(true);

  return (
    <>
      <section className="hero hero-small">
        <h1>Circuits</h1>
        <p className="lede">What a pit stop costs at each track, and how quickly each compound wears.</p>
      </section>
      <Ready load={load} label="Loading circuits">
        {({ circuits }) => {
          const shown = reliableOnly ? circuits.filter((c) => c.pit_loss?.is_reliable) : circuits.filter((c) => c.pit_loss);
          return (
            <>
              <label className="check">
                <input type="checkbox" checked={reliableOnly} onChange={(e) => setReliableOnly(e.target.checked)} />
                Only circuits with enough data
              </label>
              <section aria-labelledby="pitloss">
                <h2 id="pitloss">Pit-stop cost</h2>
                <PitLossChart circuits={shown} />
              </section>
              <section aria-labelledby="deg">
                <h2 id="deg">Tyre wear</h2>
                <p className="muted small">
                  Median wear in seconds per lap, from clean laps. Bars share one scale. A single stint is noisy, about 0.02 s per lap, so only circuit
                  medians are shown.
                </p>
                <DegradationMatrix circuits={circuits} reliableOnly={reliableOnly} />
              </section>
            </>
          );
        }}
      </Ready>
    </>
  );
}
