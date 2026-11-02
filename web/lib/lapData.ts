"use client";

import { useJson } from "./data";
import type { LapDoc, LapIndex } from "./laps";

export const useLapIndex = () => useJson<LapIndex>("/lap-data/index.json");
export const useLapDoc = (key: string | null) => useJson<LapDoc>(key ? `/lap-data/${encodeURIComponent(key)}.json` : null);
