import type { FieldType, Layer, LayerStyle, SchemaField, Symbol } from "@spatial/map-core";
import { useState, type FormEvent } from "react";

import { ErrorMessage } from "../ErrorMessage";

const FIELD_TYPES: FieldType[] = ["text", "integer", "decimal", "boolean", "date", "choice"];
const DEFAULT_SYMBOL: Symbol = { fill: "#3a7d44", stroke: "#1d3d22", stroke_width: 1.5, point_radius: 5, fill_opacity: 0.4 };

function SymbolFields({ value, onChange, label }: { value: Symbol; onChange(s: Symbol): void; label: string }) {
  return (
    <fieldset className="inline-form">
      <legend>{label}</legend>
      <label>
        Fill
        <input type="color" value={value.fill} onChange={(e) => onChange({ ...value, fill: e.target.value })} aria-label={`${label} fill`} />
      </label>
      <label>
        Outline
        <input type="color" value={value.stroke} onChange={(e) => onChange({ ...value, stroke: e.target.value })} aria-label={`${label} outline`} />
      </label>
      <label>
        Width
        <input
          type="number"
          min={0}
          max={20}
          step={0.5}
          value={value.stroke_width}
          onChange={(e) => onChange({ ...value, stroke_width: Number(e.target.value) })}
          aria-label={`${label} outline width`}
        />
      </label>
      <label>
        Fill opacity
        <input
          type="number"
          min={0}
          max={1}
          step={0.1}
          value={value.fill_opacity}
          onChange={(e) => onChange({ ...value, fill_opacity: Number(e.target.value) })}
          aria-label={`${label} fill opacity`}
        />
      </label>
    </fieldset>
  );
}

export function StyleEditor({
  layer,
  onSave,
  onClose,
}: {
  layer: Layer;
  onSave(style: LayerStyle): Promise<boolean>;
  onClose(): void;
}) {
  const [style, setStyle] = useState<LayerStyle>(layer.style);
  const categoryFields = layer.schema.filter((f) => f.type === "choice" || f.type === "text");

  /** Switches to one colour (fieldName empty) or to colouring by a field. */
  function colourBy(fieldName: string) {
    if (!fieldName) {
      const symbol = style.kind === "single" ? style : style.default;
      setStyle({ kind: "single", ...symbol, label_field: style.label_field });
      return;
    }
    const field = categoryFields.find((f) => f.name === fieldName);
    if (!field) return;
    const base = style.kind === "single" ? style : style.default;
    setStyle({
      kind: "categorized",
      field: field.name,
      categories: (field.choices ?? []).map((value) => ({ value, ...DEFAULT_SYMBOL })),
      default: { fill: base.fill, stroke: base.stroke, stroke_width: base.stroke_width, point_radius: base.point_radius, fill_opacity: base.fill_opacity },
      label_field: style.label_field,
    });
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (await onSave(style)) onClose();
  }

  return (
    <form className="card wide" onSubmit={submit} aria-label={`Style of ${layer.name}`}>
      <h2>Style: {layer.name}</h2>
      <label>
        Colour by
        <select
          aria-label="Colour by"
          value={style.kind === "single" ? "" : style.field}
          onChange={(e) => colourBy(e.target.value)}
        >
          <option value="">One colour for all</option>
          {categoryFields.map((f) => (
            <option key={f.name} value={f.name}>
              {f.label}
            </option>
          ))}
        </select>
      </label>
      {style.kind === "single" ? (
        <SymbolFields label="Symbol" value={style} onChange={(s) => setStyle({ ...style, ...s })} />
      ) : (
        <>
          {style.categories.map((category, i) => (
            <SymbolFields
              key={String(category.value)}
              label={String(category.value)}
              value={category}
              onChange={(s) =>
                setStyle({ ...style, categories: style.categories.map((c, j) => (j === i ? { ...c, ...s } : c)) })
              }
            />
          ))}
          <SymbolFields label="Other values" value={style.default} onChange={(s) => setStyle({ ...style, default: s })} />
        </>
      )}
      <label>
        Label
        <select
          aria-label="Label"
          value={style.label_field ?? ""}
          onChange={(e) => setStyle({ ...style, label_field: e.target.value || null })}
        >
          <option value="">No labels</option>
          {layer.schema.map((f) => (
            <option key={f.name} value={f.name}>
              {f.label}
            </option>
          ))}
        </select>
      </label>
      <div className="inline-form">
        <button type="submit">Save style</button>
        <button type="button" className="link" onClick={onClose}>
          Cancel
        </button>
      </div>
    </form>
  );
}

/** Edits a layer's fields. The server refuses changes that would break or
 * drop existing values and says why; removals then need confirming. */
export function SchemaEditor({
  layer,
  onSave,
  onClose,
}: {
  layer: Layer;
  onSave(schema: SchemaField[], confirmDrop: string[]): Promise<unknown>;
  onClose(): void;
}) {
  const [fields, setFields] = useState<SchemaField[]>(layer.schema);
  const [error, setError] = useState<unknown>(null);
  const [needsConfirm, setNeedsConfirm] = useState<string[]>([]);
  const removed = layer.schema.map((f) => f.name).filter((name) => !fields.some((f) => f.name === name));

  function update(i: number, change: Partial<SchemaField>) {
    setFields(fields.map((f, j) => (j === i ? { ...f, ...change } : f)));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    const result = await onSave(fields, needsConfirm);
    if (result === true) {
      onClose();
      return;
    }
    setError(result);
    const text = JSON.stringify((result as { fields?: unknown })?.fields ?? "");
    setNeedsConfirm(removed.filter((name) => text.includes(`confirm_drop=${name}`)));
  }

  return (
    <form className="card wide" onSubmit={submit} aria-label={`Fields of ${layer.name}`}>
      <h2>Fields: {layer.name}</h2>
      <table className="data">
        <thead>
          <tr>
            <th>Name</th>
            <th>Label</th>
            <th>Type</th>
            <th>Required</th>
            <th>Choices (comma-separated)</th>
            <th aria-label="Remove" />
          </tr>
        </thead>
        <tbody>
          {fields.map((field, i) => (
            <tr key={i}>
              <td>
                <input aria-label={`Field ${i + 1} name`} value={field.name} onChange={(e) => update(i, { name: e.target.value })} />
              </td>
              <td>
                <input aria-label={`Field ${i + 1} label`} value={field.label} onChange={(e) => update(i, { label: e.target.value })} />
              </td>
              <td>
                <select aria-label={`Field ${i + 1} type`} value={field.type} onChange={(e) => update(i, { type: e.target.value as FieldType })}>
                  {FIELD_TYPES.map((t) => (
                    <option key={t}>{t}</option>
                  ))}
                </select>
              </td>
              <td>
                <input
                  type="checkbox"
                  aria-label={`Field ${i + 1} required`}
                  checked={field.required}
                  onChange={(e) => update(i, { required: e.target.checked })}
                />
              </td>
              <td>
                {field.type === "choice" && (
                  <input
                    aria-label={`Field ${i + 1} choices`}
                    value={(field.choices ?? []).join(", ")}
                    onChange={(e) => update(i, { choices: e.target.value.split(",").map((c) => c.trim()).filter(Boolean) })}
                  />
                )}
              </td>
              <td>
                <button type="button" className="link danger" onClick={() => setFields(fields.filter((_, j) => j !== i))}>
                  Remove
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <button type="button" className="link" onClick={() => setFields([...fields, { name: "", label: "", type: "text", required: false }])}>
        Add field
      </button>
      <ErrorMessage error={error} />
      {needsConfirm.length > 0 && (
        <p role="alert">
          Saving again will permanently delete the values of {needsConfirm.join(", ")} from every feature.
        </p>
      )}
      <div className="inline-form">
        <button type="submit">{needsConfirm.length ? "Delete values and save" : "Save fields"}</button>
        <button type="button" className="link" onClick={onClose}>
          Cancel
        </button>
      </div>
    </form>
  );
}
