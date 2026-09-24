import type { Basemap } from "@spatial/map-core";

export function BasemapPicker(props: {
  basemaps: Basemap[];
  selectedId: number | null;
  opacity: number;
  problem: string | null;
  onSelect(id: number | null): void;
  onOpacity(opacity: number): void;
}) {
  const selected = props.basemaps.find((b) => b.id === props.selectedId);
  return (
    <section className="basemap-picker" aria-label="Basemap">
      <h2>Basemap</h2>
      <select
        aria-label="Basemap"
        value={props.selectedId ?? ""}
        onChange={(e) => props.onSelect(e.target.value ? Number(e.target.value) : null)}
      >
        <option value="">None</option>
        {props.basemaps.map((b) => (
          <option key={b.id} value={b.id}>
            {b.name}
            {b.requires_key && !b.has_key ? " (needs a key)" : ""}
          </option>
        ))}
      </select>
      <input
        type="range"
        min={0}
        max={1}
        step={0.1}
        value={props.opacity}
        aria-label="Basemap opacity"
        onChange={(e) => props.onOpacity(Number(e.target.value))}
      />
      {props.problem && (
        <p role="alert" className="error small">
          {props.problem}
        </p>
      )}
      {selected?.notes && <p className="muted small">{selected.notes}</p>}
    </section>
  );
}
