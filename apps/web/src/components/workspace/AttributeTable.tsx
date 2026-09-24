import { ApiError, type Layer, type MapFeature, type SchemaField } from "@spatial/map-core";
import { useMemo, useState, type KeyboardEvent } from "react";

import { useSession } from "../../session";
import { errorText } from "../ErrorMessage";
import { useLoad } from "../useLoad";

const PAGE = 500;

function display(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

/** Text typed into a cell -> the JSON value the server expects. */
export function parseCell(field: SchemaField, text: string): unknown {
  const trimmed = text.trim();
  if (trimmed === "") return null;
  switch (field.type) {
    case "integer":
    case "decimal": {
      const n = Number(trimmed);
      return Number.isFinite(n) ? n : trimmed; // let the server explain bad input
    }
    case "boolean":
      return ["yes", "true", "1"].includes(trimmed.toLowerCase());
    default:
      return trimmed;
  }
}

export interface AttributeTableProps {
  layer: Layer;
  canEdit: boolean;
  selectedFeatureId: number | null;
  dataVersion: number;
  onSelect(featureId: number): void;
  onSaved(): void;
}

export function AttributeTable(props: AttributeTableProps) {
  const { api } = useSession();
  const [offset, setOffset] = useState(0);
  const page = useLoad(() => api.listFeatures(props.layer.id, { limit: PAGE, offset }), [
    api,
    props.layer.id,
    offset,
    props.dataVersion,
  ]);
  const [filter, setFilter] = useState("");
  const [sort, setSort] = useState<{ field: string; desc: boolean } | null>(null);
  const [editing, setEditing] = useState<{ featureId: number; field: string; text: string } | null>(null);
  const [message, setMessage] = useState<{ kind: "error" | "status"; text: string } | null>(null);

  const rows = useMemo(() => {
    let features = page.data?.features ?? [];
    if (filter) {
      const needle = filter.toLowerCase();
      features = features.filter((f) => Object.values(f.properties).some((v) => display(v).toLowerCase().includes(needle)));
    }
    if (sort) {
      features = [...features].sort((a, b) => {
        const x = a.properties[sort.field];
        const y = b.properties[sort.field];
        const order = display(x).localeCompare(display(y), undefined, { numeric: true });
        return sort.desc ? -order : order;
      });
    }
    return features;
  }, [page.data, filter, sort]);

  async function save(feature: MapFeature, field: SchemaField, text: string) {
    setMessage(null);
    try {
      await api.updateFeature(feature.id, {
        version: feature.meta.version,
        properties: { [field.name]: parseCell(field, text) },
      });
      setEditing(null);
      setMessage({ kind: "status", text: `Saved ${field.label}.` });
      props.onSaved();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setEditing(null);
        setMessage({ kind: "error", text: "Someone else changed this feature since it loaded. The table now shows their version." });
        props.onSaved();
      } else {
        setMessage({ kind: "error", text: errorText(err) });
      }
    }
  }

  function onKey(event: KeyboardEvent<HTMLInputElement | HTMLSelectElement>, feature: MapFeature, field: SchemaField) {
    if (event.key === "Enter") void save(feature, field, editing?.text ?? "");
    if (event.key === "Escape") setEditing(null);
  }

  const fields = props.layer.schema;
  const total = page.data?.numberMatched ?? 0;

  return (
    <section className="attribute-table" aria-label={`Attributes of ${props.layer.name}`}>
      <div className="inline-form">
        <strong>{props.layer.name}</strong>
        <span className="muted">
          {total} feature{total === 1 ? "" : "s"}
        </span>
        <input type="search" placeholder="Filter" aria-label="Filter features" value={filter} onChange={(e) => setFilter(e.target.value)} />
        {message && (
          <span role={message.kind === "error" ? "alert" : "status"} className={message.kind === "error" ? "error" : "muted"}>
            {message.text}
          </span>
        )}
      </div>
      {page.error ? (
        <p role="alert">{errorText(page.error)}</p>
      ) : (
        <div className="table-scroll">
          <table className="data">
            <thead>
              <tr>
                <th>#</th>
                {fields.map((f) => (
                  <th key={f.name}>
                    <button
                      type="button"
                      className="link"
                      onClick={() => setSort(sort?.field === f.name ? { field: f.name, desc: !sort.desc } : { field: f.name, desc: false })}
                    >
                      {f.label}
                      {sort?.field === f.name ? (sort.desc ? " ▼" : " ▲") : ""}
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((feature) => (
                <tr
                  key={feature.id}
                  className={feature.id === props.selectedFeatureId ? "selected" : ""}
                  onClick={() => props.onSelect(feature.id)}
                >
                  <td>{feature.id}</td>
                  {fields.map((field) => {
                    const isEditing = editing?.featureId === feature.id && editing.field === field.name;
                    if (isEditing && field.type === "choice") {
                      return (
                        <td key={field.name}>
                          <select
                            autoFocus
                            aria-label={`${field.label} of feature ${feature.id}`}
                            value={editing.text}
                            onChange={(e) => void save(feature, field, e.target.value)}
                            onKeyDown={(e) => onKey(e, feature, field)}
                          >
                            <option value="">—</option>
                            {(field.choices ?? []).map((c) => (
                              <option key={String(c)} value={String(c)}>
                                {String(c)}
                              </option>
                            ))}
                          </select>
                        </td>
                      );
                    }
                    if (isEditing) {
                      return (
                        <td key={field.name}>
                          <input
                            autoFocus
                            aria-label={`${field.label} of feature ${feature.id}`}
                            value={editing.text}
                            onChange={(e) => setEditing({ ...editing, text: e.target.value })}
                            onKeyDown={(e) => onKey(e, feature, field)}
                          />
                        </td>
                      );
                    }
                    return (
                      <td
                        key={field.name}
                        onDoubleClick={() =>
                          props.canEdit && setEditing({ featureId: feature.id, field: field.name, text: display(feature.properties[field.name]) })
                        }
                        title={props.canEdit ? "Double-click to edit" : undefined}
                      >
                        {display(feature.properties[field.name])}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {total > PAGE && (
        <div className="pager">
          <button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
            Previous
          </button>
          <span>
            {offset + 1}–{Math.min(offset + PAGE, total)} of {total}
          </span>
          <button type="button" disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)}>
            Next
          </button>
        </div>
      )}
    </section>
  );
}

/** Everything about the feature clicked on the map. */
export function IdentifyPanel({ layer, featureId, onClose }: { layer: Layer; featureId: number; onClose(): void }) {
  const { api } = useSession();
  const feature = useLoad(() => api.getFeature(featureId), [api, featureId]);

  return (
    <aside className="identify" aria-label="Feature details">
      <div className="inline-form">
        <strong>
          {layer.name} #{featureId}
        </strong>
        <button type="button" className="link" onClick={onClose}>
          Close
        </button>
      </div>
      {feature.error ? <p role="alert">{errorText(feature.error)}</p> : null}
      {feature.data && (
        <dl>
          {layer.schema.map((field) => (
            <div key={field.name}>
              <dt>{field.label}</dt>
              <dd>{display(feature.data!.properties[field.name]) || "—"}</dd>
            </div>
          ))}
          <div>
            <dt>Version</dt>
            <dd>
              {feature.data.meta.version} · {feature.data.meta.origin}
              {feature.data.meta.verified ? " · verified in the field" : ""}
            </dd>
          </div>
        </dl>
      )}
    </aside>
  );
}
