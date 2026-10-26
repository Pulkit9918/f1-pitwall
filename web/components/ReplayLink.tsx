"use client";

import Link from "next/link";
import { useReplayIndex } from "@/lib/replayData";
import { useTraceIndex } from "@/lib/traceData";

export function ReplayLink({ sessionKey }: { sessionKey: string }) {
  const index = useReplayIndex();
  const traces = useTraceIndex();
  const replay = index.state === "ready" && index.data.sessions.some((s) => s.key === sessionKey);
  const telemetry = traces.state === "ready" && traces.data.sessions.some((s) => s.key === sessionKey);
  if (!replay && !telemetry) return null;
  return (
    <p className="replay-link">
      {replay && <Link href={`/replay?key=${encodeURIComponent(sessionKey)}`}>Watch the replay</Link>}
      {replay && telemetry && " · "}
      {telemetry && <Link href={`/telemetry?key=${encodeURIComponent(sessionKey)}`}>Compare laps</Link>}
    </p>
  );
}
