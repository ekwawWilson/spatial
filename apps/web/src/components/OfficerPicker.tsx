import type { AssignableKind, Officer } from "@spatial/map-core";
import { useState } from "react";

import { useSession } from "../session";
import { useLoad } from "./useLoad";

/** Who is handling a record, and (for those allowed) a choice to hand it to someone else. */
export function OfficerPicker(props: { kind: AssignableKind; id: number; officer: Officer | null; onChange?: (officer: Officer | null) => void; compact?: boolean }) {
  const { api, districtId, can } = useSession();
  const allowed = can(props.kind === "case" ? "enforcement.act" : "permit.process");
  const officers = useLoad(() => (allowed ? api.officers() : Promise.resolve([] as Officer[])), [api, districtId, allowed]);
  const [current, setCurrent] = useState(props.officer);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!allowed) {
    return <span className={current ? undefined : "muted"}>{current?.name ?? "Not assigned"}</span>;
  }

  async function choose(value: string) {
    setBusy(true);
    setError(null);
    try {
      const done = await api.assign(props.kind, props.id, value ? Number(value) : null);
      setCurrent(done.officer);
      props.onChange?.(done.officer);
    } catch {
      setError("Couldn't save: try again.");
    } finally {
      setBusy(false);
    }
  }

  const list = officers.data ?? [];
  // The current officer stays in the list even if they've since left the district.
  const shown = current && !list.some((o) => o.id === current.id) ? [current, ...list] : list;
  return (
    <span className="officer-picker">
      <select aria-label={`Officer for ${props.kind === "case" ? "the case" : "the application"}`} value={current?.id ?? ""} disabled={busy} onChange={(e) => void choose(e.target.value)} className={props.compact ? "compact" : undefined}>
        <option value="">Not assigned</option>
        {shown.map((o) => (
          <option key={o.id} value={o.id}>
            {o.name}
          </option>
        ))}
      </select>
      {error && <span className="error small">{error}</span>}
    </span>
  );
}
