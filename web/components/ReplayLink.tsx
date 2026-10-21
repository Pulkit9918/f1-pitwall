"use client";

import Link from "next/link";
import { useReplayIndex } from "@/lib/replayData";

export function ReplayLink({ sessionKey }: { sessionKey: string }) {
  const index = useReplayIndex();
  if (index.state !== "ready" || !index.data.sessions.some((s) => s.key === sessionKey)) return null;
  return (
    <p className="replay-link">
      <Link href={`/replay?key=${encodeURIComponent(sessionKey)}`}>Watch the replay</Link>
    </p>
  );
}
