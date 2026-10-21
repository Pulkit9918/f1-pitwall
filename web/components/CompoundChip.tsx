import { compoundColor, compoundLetter, onCompound } from "@/lib/colors";

export function CompoundChip({ compound }: { compound: string | null | undefined }) {
  if (!compound) return <span className="muted">-</span>;
  return (
    <span className="chip-compound" title={compound} style={{ background: compoundColor(compound), color: onCompound(compound) }}>
      {compoundLetter(compound)}
    </span>
  );
}
