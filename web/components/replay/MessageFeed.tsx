import { fmtClock, messagesUpTo, type Replay } from "@/lib/replay";

export function MessageFeed({ replay, t, clock0 }: { replay: Replay; t: number; clock0: number }) {
  const msgs = messagesUpTo(replay.file, t, 60);
  if (msgs.length === 0) return <p className="muted">No race control messages yet.</p>;
  return (
    <ol className="rp-msgs" aria-label="Race control messages, newest first">
      {msgs.map((m, i) => (
        <li key={`${m[0]}-${i}`}>
          <span className="num rp-msg-time">{fmtClock(m[0] - clock0)}</span>
          <span className="rp-msg-lap num">{m[3] != null ? `Lap ${m[3]}` : ""}</span>
          <span className="rp-msg-flag">{m[2] || m[1]}</span>
          <span className="rp-msg-text">{m[4]}</span>
        </li>
      ))}
    </ol>
  );
}
