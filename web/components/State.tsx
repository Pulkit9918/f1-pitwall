import type { Load } from "@/lib/data";

export function LoadError({ message }: { message: string }) {
  return (
    <div className="notice" role="alert">
      <strong>The data could not be loaded.</strong>
      <span>{message}</span>
      <span>
        Run <code>python scripts/export_static.py</code> from the repository root, then reload.
      </span>
    </div>
  );
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div className="loading" role="status">
      {label}
    </div>
  );
}

export function Ready<T>({ load, children, label }: { load: Load<T>; children: (data: T) => React.ReactNode; label?: string }) {
  if (load.state === "loading") return <Loading label={label} />;
  if (load.state === "error") return <LoadError message={load.message} />;
  return <>{children(load.data)}</>;
}
