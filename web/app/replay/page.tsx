"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo } from "react";
import { ReplayView } from "@/components/replay/ReplayView";
import { Loading, LoadError } from "@/components/State";
import { useSession } from "@/lib/data";
import { decodeReplay, type ReplayFile } from "@/lib/replay";
import { useReplayFile } from "@/lib/replayData";
import type { SessionDoc } from "@/lib/types";
import "./replay.css";

function Loaded({ doc, file }: { doc: SessionDoc; file: ReplayFile }) {
  const replay = useMemo(() => decodeReplay(file), [file]);
  return <ReplayView key={file.key} doc={doc} replay={replay} />;
}

function ReplayInner() {
  const key = useSearchParams().get("key");
  const doc = useSession(key);
  const file = useReplayFile(key);
  if (!key) {
    return (
      <section className="hero hero-small">
        <h1>No session chosen</h1>
        <p className="lede">Pick one from the <Link href="/sessions">sessions list</Link>, then choose Watch the replay.</p>
      </section>
    );
  }
  if (file.state === "error" && file.message.startsWith("404")) {
    return (
      <section className="hero hero-small">
        <h1>No replay for this session</h1>
        <p className="lede">
          Replays cover races and qualifying with position data. <Link href={`/race?key=${encodeURIComponent(key)}`}>Open the analysis instead</Link>.
        </p>
      </section>
    );
  }
  if (file.state === "error") return <LoadError message={file.message} />;
  if (doc.state === "error") return <LoadError message={doc.message} />;
  if (file.state === "loading" || doc.state === "loading") return <Loading label="Loading the replay" />;
  return <Loaded doc={doc.data} file={file.data} />;
}

export default function ReplayPage() {
  return (
    <Suspense fallback={<Loading />}>
      <ReplayInner />
    </Suspense>
  );
}
