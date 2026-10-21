import { DRIVER_COLORS } from "@/lib/colors";

export function DriverPicker({
  order,
  slots,
  onToggle,
}: {
  order: string[];
  slots: (string | null)[];
  onToggle: (code: string) => void;
}) {
  const full = slots.every((s) => s !== null);
  return (
    <div className="picker" role="group" aria-label="Drivers to compare">
      {order.map((code) => {
        const slot = slots.indexOf(code);
        const on = slot >= 0;
        const blocked = !on && full;
        return (
          <button
            key={code}
            type="button"
            className={`pick${on ? " pick-on" : ""}`}
            aria-pressed={on}
            aria-disabled={blocked}
            onClick={() => !blocked && onToggle(code)}
            title={blocked ? "Remove a driver first; three can be compared at once" : undefined}
          >
            <span className="pick-dot" style={{ background: on ? DRIVER_COLORS[slot] : "transparent", borderColor: on ? DRIVER_COLORS[slot] : "var(--ink-3)" }} />
            {code}
          </button>
        );
      })}
    </div>
  );
}
