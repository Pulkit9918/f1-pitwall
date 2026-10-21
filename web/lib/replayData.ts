"use client";

import { useJson } from "./data";
import type { ReplayFile } from "./replay";

export interface ReplayIndex {
  generator: string;
  step: number;
  sessions: { key: string; kind: "race" | "quali"; n: number; drivers: number }[];
}

// Replay files live outside /data, because scripts/export_static.py wipes that folder on every run.
export const useReplayIndex = () => useJson<ReplayIndex>("/replay-data/index.json");
export const useReplayFile = (key: string | null) =>
  useJson<ReplayFile>(key ? `/replay-data/${encodeURIComponent(key)}.json` : null);
