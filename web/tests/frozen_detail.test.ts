// Prints what the replay file and the lap table hold for chosen cars, to check the frozen-car rule.
//   cd web && FROZEN_DETAIL="2025-R04-R:RUS,2022-R08-R:LEC" npx vitest run tests/frozen_detail.test.ts --reporter=verbose
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, it } from "vitest";
import { buildLapIndex, completed, decodeReplay, frozenSpans, type ReplayFile } from "../lib/replay";
import type { SessionDoc } from "../lib/types";

const root = join(__dirname, "..", "public");
const wanted = (process.env.FROZEN_DETAIL ?? "").split(",").filter(Boolean);

describe.skipIf(wanted.length === 0)("detail for chosen cars", () => {
  for (const w of wanted) {
    it(w, () => {
      const [key, code] = w.split(":");
      const replay = decodeReplay(JSON.parse(readFileSync(join(root, "replay-data", `${key}.json`), "utf8")) as ReplayFile);
      const doc = JSON.parse(readFileSync(join(root, "data", "sessions", `${key}.json`), "utf8")) as SessionDoc;
      const recs = buildLapIndex(doc).get(code) ?? [];
      const d = replay.file.drivers[code];
      const out: string[] = [`${key} ${code}`];
      if (!d) {
        console.log(out.concat("  no position data for this driver. Drivers: " + Object.keys(replay.file.drivers).join(" ")).join("\n"));
        return;
      }
      out.push(`  frames n=${replay.file.n}, data frames ${d.a}..${d.b}, t0=${replay.t0}, step=${replay.step}; lap records: ${recs.length}, completed: ${recs.filter(completed).length}`);
      // with a minimum of one lap, so that stretches the default rule rejects are shown too
      const spans = frozenSpans(replay, code, recs, 60, 1);
      const kept = frozenSpans(replay, code, recs);
      out.push(`  stretches with at least one completed lap: ${JSON.stringify(spans)}`);
      out.push(`  stretches kept by the rule (two laps or more): ${JSON.stringify(kept)}`);
      for (const [a, b] of spans) {
        out.push(`  laps near ${a}..${b} (lap, start, end, time):`);
        for (const l of recs.filter((x) => (x.end ?? 0) >= a - 120 && (x.start ?? 0) <= b + 120).slice(0, 14)) {
          out.push(`    ${l.lap}, ${l.start}, ${l.end}, ${l.time}`);
        }
      }
      console.log(out.join("\n"));
    });
  }
});
