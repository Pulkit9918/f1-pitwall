"use client";

import { useJson } from "./data";
import type { LapDoc, LapIndex } from "./laps";

// Lap files live outside /data, because scripts/export_static.py wipes that folder on every run.
export const useLapIndex = () => useJson<LapIndex>("/lap-data/index.json");
export const useLapDoc = (key: string | null) => useJson<LapDoc>(key ? `/lap-data/${encodeURIComponent(key)}.json` : null);
