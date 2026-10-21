import type { ReactNode } from "react";

// A tooltip placed in a chart wrapper (position: relative); it flips to the left of the cursor in the right half.
export function Tip({ x, y, width, children }: { x: number; y: number; width: number; children: ReactNode }) {
  const left = x > width / 2;
  return (
    <div
      className="tip"
      role="presentation"
      style={{ left: left ? x - 14 : x + 14, top: Math.max(4, y - 10), transform: left ? "translateX(-100%)" : undefined }}
    >
      {children}
    </div>
  );
}
