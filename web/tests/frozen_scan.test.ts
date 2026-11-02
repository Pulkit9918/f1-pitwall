// Lists every car in the exported replays whose position data stops while the lap table goes on.
// It only runs on request:  cd web && FROZEN_SCAN=1 npx vitest run tests/frozen_scan.test.ts --reporter=verbose
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, it } from "vitest";
import { buildLapIndex, decodeReplay, frozenSpans, type ReplayFile } from "../lib/replay";
import type { SessionDoc } from "../lib/types";

const root = join(__dirname, "..", "public");

describe.skipIf(!process.env.FROZEN_SCAN)("frozen cars in the exported replays", () => {
  it("lists them", () => {
    const index = JSON.parse(readFileSync(join(root, "replay-data", "index.json"), "utf8"));
    let sessions = 0;
    let missing = 0;
    const found: string[] = [];
    for (const s of index.sessions as { key: string; kind: string }[]) {
      const docPath = join(root, "data", "sessions", `${s.key}.json`);
      if (s.kind !== "race" || !existsSync(docPath)) {
        missing += s.kind === "race" ? 1 : 0;
        continue;
      }
      const replay = decodeReplay(JSON.parse(readFileSync(join(root, "replay-data", `${s.key}.json`), "utf8")) as ReplayFile);
      const idx = buildLapIndex(JSON.parse(readFileSync(docPath, "utf8")) as SessionDoc);
      sessions++;
      for (const [code, recs] of idx) {
        if (!replay.file.drivers[code]) continue;
        for (const [a, b] of frozenSpans(replay, code, recs)) {
          found.push(`${s.key} ${code} ${Math.round(a - replay.t0)} s to ${Math.round(b - replay.t0)} s of ${replay.file.n - 1}`);
        }
      }
    }
    console.log(`scanned ${sessions} race replays (${missing} without a session file); ${found.length} frozen stretches`);
    for (const f of found) console.log("  " + f);
  });
});
