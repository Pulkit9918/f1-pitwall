import type { ReactNode } from "react";

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
