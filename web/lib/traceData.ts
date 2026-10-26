"use client";

import { useEffect, useState } from "react";
import { loadJson, useJson } from "./data";
import type { TraceDriverFile, TraceIndex, TraceSession } from "./traces";

// Trace files live outside /data, because scripts/export_static.py wipes that folder on every run.
export const useTraceIndex = () => useJson<TraceIndex>("/trace-data/index.json");
export const useTraceSession = (key: string | null) =>
  useJson<TraceSession>(key ? `/trace-data/${encodeURIComponent(key)}/index.json` : null);

export interface DriverFiles {
  files: Record<string, TraceDriverFile | undefined>;
  loading: boolean;
  error: string | null;
}

// The files of the given drivers, each fetched once and kept. Files of drivers no longer chosen stay in memory.
export function useDriverFiles(key: string | null, drivers: string[]): DriverFiles {
  const [state, setState] = useState<{ key: string | null; files: Record<string, TraceDriverFile | undefined>; error: string | null }>({ key, files: {}, error: null });
  const wanted = [...new Set(drivers)].sort().join(",");
  useEffect(() => {
    if (!key || !wanted) return;
    let live = true;
    for (const code of wanted.split(",")) {
      loadJson<TraceDriverFile>(`/trace-data/${encodeURIComponent(key)}/${encodeURIComponent(code)}.json`).then(
        (file) => live && setState((s) => (s.key === key ? { ...s, files: { ...s.files, [code]: file } } : { key, files: { [code]: file }, error: null })),
        (e: Error) => live && setState((s) => ({ key, files: s.key === key ? s.files : {}, error: e.message })),
      );
    }
    return () => {
      live = false;
    };
  }, [key, wanted]);
  const files = state.key === key ? state.files : {};
  const loading = wanted !== "" && wanted.split(",").some((c) => !files[c]) && !(state.key === key && state.error);
  return { files, loading, error: state.key === key ? state.error : null };
}
