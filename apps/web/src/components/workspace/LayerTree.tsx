import { DOMAIN_LABELS, type Domain, type GeometryType, type Layer } from "@spatial/map-core";
import { useState, type FormEvent } from "react";

const GEOMETRY_LABELS: Record<GeometryType, string> = { point: "Points", line: "Lines", polygon: "Polygons" };

export interface LayerTreeProps {
  layers: Layer[]; // top first
  selectedLayerId: number | null;
  canEdit: boolean;
  onSelect(layerId: number): void;
  onChange(layer: Layer, change: Partial<Layer>): void;
  onMove(layerId: number, direction: -1 | 1): void;
  onZoom(layer: Layer): void;
  onEditStyle(layer: Layer): void;
  onEditFields(layer: Layer): void;
  onDelete(layer: Layer): void;
  onAdd(data: { name: string; domain: Domain; geometry_type: GeometryType }): Promise<boolean>;
}

/** Layers grouped by data domain (A–J), drawn top first as on the map. */
export function LayerTree(props: LayerTreeProps) {
  const groups = new Map<Domain, Layer[]>();
  for (const layer of props.layers) groups.set(layer.domain, [...(groups.get(layer.domain) ?? []), layer]);

  return (
    <div className="layer-tree">
      <h2>Layers</h2>
      {props.layers.length === 0 && <p className="muted">No layers yet.</p>}
      {[...groups].map(([domain, layers]) => (
        <section key={domain} aria-label={DOMAIN_LABELS[domain]}>
          <h3>{DOMAIN_LABELS[domain]}</h3>
          <ul>
            {layers.map((layer) => {
              const index = props.layers.indexOf(layer);
              return (
                <li key={layer.id} className={layer.id === props.selectedLayerId ? "selected" : ""}>
                  <label className="checkbox">
                    <input
                      type="checkbox"
                      checked={layer.visible}
                      aria-label={`Show ${layer.name}`}
                      onChange={() => props.onChange(layer, { visible: !layer.visible })}
                    />
                  </label>
                  <button type="button" className="link layer-name" onClick={() => props.onSelect(layer.id)}>
                    {layer.name}
                  </button>
                  <span className="muted small">
                    {GEOMETRY_LABELS[layer.geometry_type]} · {layer.feature_count}
                  </span>
                  <div className="layer-actions">
                    <input
                      type="range"
                      min={0}
                      max={1}
                      step={0.1}
                      value={layer.opacity}
                      aria-label={`Opacity of ${layer.name}`}
                      onChange={(e) => props.onChange(layer, { opacity: Number(e.target.value) })}
                    />
                    <button type="button" className="link" aria-label={`Zoom to ${layer.name}`} onClick={() => props.onZoom(layer)}>
                      Zoom
                    </button>
                    {props.canEdit && (
                      <>
                        <button
                          type="button"
                          className="link"
                          aria-label={`Move ${layer.name} up`}
                          disabled={index === 0}
                          onClick={() => props.onMove(layer.id, -1)}
                        >
                          ↑
                        </button>
                        <button
                          type="button"
                          className="link"
                          aria-label={`Move ${layer.name} down`}
                          disabled={index === props.layers.length - 1}
                          onClick={() => props.onMove(layer.id, 1)}
                        >
                          ↓
                        </button>
                        <button type="button" className="link" onClick={() => props.onEditStyle(layer)}>
                          Style
                        </button>
                        <button type="button" className="link" onClick={() => props.onEditFields(layer)}>
                          Fields
                        </button>
                        <button type="button" className="link danger" onClick={() => props.onDelete(layer)}>
                          Delete
                        </button>
                      </>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
      {props.canEdit && <AddLayerForm onAdd={props.onAdd} />}
    </div>
  );
}

function AddLayerForm({ onAdd }: { onAdd: LayerTreeProps["onAdd"] }) {
  const [name, setName] = useState("");
  const [domain, setDomain] = useState<Domain>("B");
  const [geometryType, setGeometryType] = useState<GeometryType>("polygon");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!(await onAdd({ name, domain, geometry_type: geometryType }))) return;
    setName("");
  }

  return (
    <form className="stack" onSubmit={submit} aria-label="Add layer">
      <h3>Add a layer</h3>
      <input required placeholder="Layer name" aria-label="Layer name" value={name} onChange={(e) => setName(e.target.value)} />
      <select aria-label="Domain" value={domain} onChange={(e) => setDomain(e.target.value as Domain)}>
        {Object.entries(DOMAIN_LABELS).map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </select>
      <select aria-label="Geometry" value={geometryType} onChange={(e) => setGeometryType(e.target.value as GeometryType)}>
        {Object.entries(GEOMETRY_LABELS).map(([value, label]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </select>
      <button type="submit">Add layer</button>
    </form>
  );
}
