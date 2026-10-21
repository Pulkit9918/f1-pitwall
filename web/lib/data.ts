"use client";

import { useEffect, useState } from "react";
import type { AnalysisDoc } from "./analysis";
import type { Circuit, Manifest, SessionDoc, SessionMeta } from "./types";

const cache = new Map<string, Promise<unknown>>();

export function loadJson<T>(path: string): Promise<T> {
  let p = cache.get(path);
  if (!p) {
    p = fetch(path).then((r) => {
      if (!r.ok) throw new Error(`${r.status} ${r.statusText} for ${path}`);
      return r.json();
    });
    cache.set(path, p);
    p.catch(() => cache.delete(path));
  }
  return p as Promise<T>;
}

export type Load<T> =
  | { state: "loading" }
  | { state: "error"; message: string }
  | { state: "ready"; data: T };

export function useJson<T>(path: string | null): Load<T> {
  const [res, setRes] = useState<{ path: string | null; load: Load<T> }>({ path, load: { state: "loading" } });
  useEffect(() => {
    if (path === null) return;
    let live = true;
    loadJson<T>(path).then(
      (data) => live && setRes({ path, load: { state: "ready", data } }),
      (e: Error) => live && setRes({ path, load: { state: "error", message: e.message } }),
    );
    return () => {
      live = false;
    };
  }, [path]);
  return res.path === path ? res.load : { state: "loading" };
}

export const useManifest = () => useJson<Manifest>("/data/manifest.json");
export const useCircuits = () => useJson<{ circuits: Circuit[] }>("/data/circuits.json");
export const useSessions = () => useJson<{ sessions: SessionMeta[] }>("/data/sessions.json");
export const useSession = (key: string | null) =>
  useJson<SessionDoc>(key ? `/data/sessions/${encodeURIComponent(key)}.json` : null);
export const useAnalysis = (key: string | null) =>
  useJson<AnalysisDoc>(key ? `/analysis-data/${encodeURIComponent(key)}.json` : null);
