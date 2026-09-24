import {
  DOMAIN_LABELS,
  type CoordinateSystem,
  type DataJob,
  type Domain,
  type GeometryType,
  type ImportPlanItem,
  type InspectedLayer,
  type Inspection,
  type Layer,
} from "@spatial/map-core";
import { useEffect, useState, type FormEvent } from "react";

import { useSession } from "../../session";
import { ErrorMessage } from "../ErrorMessage";

const FAMILY: Record<string, GeometryType> = {
  Point: "point",
  MultiPoint: "point",
  LineString: "line",
  MultiLineString: "line",
  Polygon: "polygon",
  MultiPolygon: "polygon",
};

/** The geometry family most features in a source layer have. */
export function dominantFamily(layer: InspectedLayer): GeometryType {
  const counts: Record<GeometryType, number> = { point: 0, line: 0, polygon: 0 };
  for (const [type, n] of Object.entries(layer.geometry_types)) {
    const family = FAMILY[type];
    if (family) counts[family] += n;
  }
  return (Object.entries(counts).sort((a, b) => b[1] - a[1])[0]?.[0] ?? "polygon") as GeometryType;
}

export interface LayerChoice {
  include: boolean;
  plan: ImportPlanItem;
}

/** Sensible starting choices for one source layer. The CRS is preselected only
 * when the file's own CRS is available here; otherwise the user must pick. */
export function defaultChoice(layer: InspectedLayer, inspection: Inspection, systems: CoordinateSystem[]): LayerChoice {
  const detected = layer.crs.epsg ? systems.find((s) => s.code === `EPSG:${layer.crs.epsg}`) : undefined;
  return {
    include: true,
    plan: {
      source: layer.name,
      crs: detected?.code ?? "",
      crs_confirmed: !(inspection.crs_confirmation_required || !layer.crs.found),
      new_layer: { name: layer.name, domain: "other", geometry_type: dominantFamily(layer) },
      fields: layer.fields.map((f) => ({ source: f.name, target: f.suggested_name.toLowerCase(), type: f.type })),
      invalid_geometry: "skip",
      duplicates: "keep",
      bad_values: "blank",
      cad_layers: layer.cad_layers.length ? layer.cad_layers : undefined,
    },
  };
}

/** Why a choice can't run yet, or null when it can. */
export function choiceProblem(choice: LayerChoice, layer: InspectedLayer, inspection: Inspection): string | null {
  if (!choice.include) return null;
  if (!choice.plan.crs) return "Choose the coordinate system the file's coordinates are in.";
  const needsConfirmation = inspection.crs_confirmation_required || !layer.crs.found;
  if (needsConfirmation && !choice.plan.crs_confirmed) {
    return layer.crs.found
      ? "This file type doesn't reliably record its coordinate system: confirm it."
      : "The file doesn't say which coordinate system it uses: confirm your choice.";
  }
  if (!choice.plan.target_layer && !choice.plan.new_layer?.name) return "Name the new layer.";
  return null;
}

/** An import started from a checklist item: into its layer, or a new layer
 * named after the item, in its domain. */
export interface ImportBinding {
  title: string;
  layerId: number | null;
  domain: Domain;
  geometryType?: GeometryType;
}

/** Applies a checklist binding: the first source layer goes to the item's
 * layer (or a new one named after it); any others are left out. */
export function bindChoices(choices: LayerChoice[], binding: ImportBinding | undefined): LayerChoice[] {
  if (!binding) return choices;
  return choices.map((choice, i) => {
    if (i > 0) return { ...choice, include: false };
    const plan = binding.layerId
      ? { ...choice.plan, target_layer: binding.layerId, new_layer: undefined }
      : {
          ...choice.plan,
          target_layer: undefined,
          new_layer: {
            name: binding.title,
            domain: binding.domain,
            geometry_type: binding.geometryType ?? choice.plan.new_layer?.geometry_type ?? "polygon",
          },
        };
    return { ...choice, plan };
  });
}

export function ImportWizard(props: {
  projectId: number;
  layers: Layer[];
  systems: CoordinateSystem[];
  binding?: ImportBinding;
  onDone(): void;
  onClose(): void;
}) {
  const { api } = useSession();
  const [file, setFile] = useState<File | null>(null);
  const [encoding, setEncoding] = useState("");
  const [job, setJob] = useState<DataJob | null>(null);
  const [choices, setChoices] = useState<LayerChoice[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const inspection = job?.inspection as Inspection | undefined;

  async function uploadFile(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const inspected = await api.uploadImport(props.projectId, file, encoding || undefined);
      const found = inspected.inspection as Inspection;
      setJob(inspected);
      setChoices(bindChoices(found.layers.map((layer) => defaultChoice(layer, found, props.systems)), props.binding));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function start() {
    if (!job || !inspection) return;
    setError(null);
    const plan = choices.filter((c) => c.include).map((c) => c.plan);
    if (!plan.length) {
      setError(new Error("Choose at least one layer to import."));
      return;
    }
    try {
      setJob(await api.runImport(job.id, plan));
    } catch (err) {
      setError(err);
    }
  }

  // Follow the running job.
  useEffect(() => {
    if (!job || !["queued", "running"].includes(job.status)) return;
    const timer = setTimeout(async () => {
      try {
        const next = await api.getJob(job.id);
        setJob(next);
        if (next.status === "done") props.onDone();
      } catch (err) {
        setError(err);
      }
    }, 1500);
    return () => clearTimeout(timer);
  }, [api, job, props]);

  // The coordinate system list may arrive after the file was inspected: fill in
  // the file's own CRS then, unless the user has already chosen one.
  useEffect(() => {
    if (!inspection || props.systems.length === 0) return;
    setChoices((all) => {
      let changed = false;
      const next = all.map((choice, i) => {
        const layer = inspection.layers[i];
        if (!layer || choice.plan.crs || !layer.crs.epsg) return choice;
        const detected = props.systems.find((s) => s.code === `EPSG:${layer.crs.epsg}`);
        if (!detected) return choice;
        changed = true;
        return { ...choice, plan: { ...choice.plan, crs: detected.code } };
      });
      return changed ? next : all;
    });
  }, [inspection, props.systems]);

  function update(i: number, change: Partial<ImportPlanItem>, include?: boolean) {
    setChoices((all) =>
      all.map((c, j) => (j === i ? { include: include ?? c.include, plan: { ...c.plan, ...change } } : c)),
    );
  }

  return (
    <div className="card wide" role="dialog" aria-modal="true" aria-label="Import data">
      <h2>Import data</h2>
      {props.binding && (
        <p className="muted small">
          For the checklist item <strong>{props.binding.title}</strong>
          {props.binding.layerId ? ", into its layer." : ", into a new layer named after it."}
        </p>
      )}
      {!job && (
        <form onSubmit={uploadFile} className="stack" aria-label="Choose a file">
          <p className="muted">
            Shapefile (zip it with its .shx, .dbf and .prj), GeoPackage, GeoJSON, KML/KMZ, DXF, DWG or CSV with coordinate
            columns.
          </p>
          <input type="file" aria-label="File" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <label>
            Text encoding (only if names show up garbled)
            <input value={encoding} onChange={(e) => setEncoding(e.target.value)} placeholder="e.g. CP1252" />
          </label>
          <ErrorMessage error={error} />
          <div className="inline-form">
            <button type="submit" disabled={!file || busy}>
              {busy ? "Reading the file…" : "Upload and inspect"}
            </button>
            <button type="button" className="link" onClick={props.onClose}>
              Cancel
            </button>
          </div>
        </form>
      )}

      {job?.status === "inspected" && inspection && (
        <div className="stack">
          <p>
            <strong>{job.original_name}</strong> contains {inspection.layers.length} layer
            {inspection.layers.length === 1 ? "" : "s"}.
          </p>
          {inspection.layers.map((layer, i) => (
            <SourceLayer
              key={layer.name}
              layer={layer}
              inspection={inspection}
              choice={choices[i]!}
              layers={props.layers}
              systems={props.systems}
              onChange={(change, include) => update(i, change, include)}
            />
          ))}
          <ErrorMessage error={error} />
          <div className="inline-form">
            <button
              type="button"
              onClick={start}
              disabled={choices.some((c, i) => choiceProblem(c, inspection.layers[i]!, inspection) !== null)}
            >
              Import
            </button>
            <button type="button" className="link" onClick={props.onClose}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {job && ["queued", "running"].includes(job.status) && (
        <div role="status" className="stack">
          <p>Importing… {job.live_progress ? `${job.live_progress.done} of ${job.live_progress.total} features` : ""}</p>
          <progress max={job.live_progress?.total || 1} value={job.live_progress?.done ?? 0} />
        </div>
      )}

      {job?.status === "failed" && (
        <div className="stack">
          <p role="alert" className="error">
            The import failed and nothing was imported: {job.error}
          </p>
          <button type="button" onClick={props.onClose}>
            Close
          </button>
        </div>
      )}

      {job?.status === "done" && (
        <div className="stack" role="region" aria-label="Import report">
          {(job.report.layers ?? []).map((r) => (
            <div key={r.source}>
              <h3>
                {r.source} → {r.target_name}
              </h3>
              <p>
                {r.imported} imported, {r.skipped} skipped
                {r.fixed_geometries ? `, ${r.fixed_geometries} geometries fixed` : ""}
                {r.duplicates ? `, ${r.duplicates} duplicates` : ""}
                {r.blanked_values ? `, ${r.blanked_values} values left empty` : ""}
                {r.z_dropped ? `, heights dropped from ${r.z_dropped}` : ""}.
              </p>
              {r.operation && (
                <p className="muted">
                  Converted with {r.operation.name}
                  {r.operation.accuracy_m !== null ? ` (±${r.operation.accuracy_m} m)` : ""}.
                </p>
              )}
              {r.problems.length > 0 && (
                <details>
                  <summary>{r.problems.length} row(s) with problems</summary>
                  <ul>
                    {r.problems.map((p) => (
                      <li key={`${p.row}-${p.message}`}>
                        Row {p.row}: {p.message}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          ))}
          <button type="button" onClick={props.onClose}>
            Close
          </button>
        </div>
      )}
    </div>
  );
}

function SourceLayer(props: {
  layer: InspectedLayer;
  inspection: Inspection;
  choice: LayerChoice;
  layers: Layer[];
  systems: CoordinateSystem[];
  onChange(change: Partial<ImportPlanItem>, include?: boolean): void;
}) {
  const { layer, choice, inspection } = props;
  const plan = choice.plan;
  const family = dominantFamily(layer);
  const target = props.layers.find((l) => l.id === plan.target_layer);
  const problem = choiceProblem(choice, layer, inspection);
  const types = Object.entries(layer.geometry_types)
    .map(([t, n]) => `${n} ${t}`)
    .join(", ");

  return (
    <fieldset aria-label={`Source layer ${layer.name}`}>
      <legend>
        <label className="checkbox">
          <input type="checkbox" checked={choice.include} onChange={(e) => props.onChange({}, e.target.checked)} />
          {layer.name}
        </label>
      </legend>
      <p className="muted small">
        {layer.feature_count} features ({types || "no geometry"}){layer.has_z ? "; heights will be dropped" : ""}
      </p>
      {choice.include && (
        <div className="stack">
          <label>
            Coordinates are in
            <select aria-label={`Coordinate system of ${layer.name}`} value={plan.crs} onChange={(e) => props.onChange({ crs: e.target.value })}>
              <option value="">Choose…</option>
              {props.systems.map((s) => (
                <option key={s.code} value={s.code}>
                  {s.code} · {s.name}
                </option>
              ))}
            </select>
          </label>
          {layer.crs.found ? (
            <p className="muted small">
              The file says: {layer.crs.name}
              {layer.crs.epsg ? ` (EPSG:${layer.crs.epsg}, ${layer.crs.confidence}% match)` : " (not an EPSG system here)"}
            </p>
          ) : (
            <p className="error small">The file doesn't say which coordinate system it uses.</p>
          )}
          {(inspection.crs_confirmation_required || !layer.crs.found) && (
            <label className="checkbox">
              <input
                type="checkbox"
                checked={Boolean(plan.crs_confirmed)}
                onChange={(e) => props.onChange({ crs_confirmed: e.target.checked })}
                aria-label={`Confirm coordinate system of ${layer.name}`}
              />
              I confirm these coordinates are in {plan.crs || "the system chosen above"}
            </label>
          )}
          {layer.cad_layers.length > 0 && (
            <label>
              CAD layers to import
              <select
                multiple
                aria-label="CAD layers"
                value={plan.cad_layers ?? []}
                onChange={(e) => props.onChange({ cad_layers: [...e.target.selectedOptions].map((o) => o.value) })}
              >
                {layer.cad_layers.map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </label>
          )}
          <label>
            Import into
            <select
              aria-label={`Target of ${layer.name}`}
              value={plan.target_layer ?? ""}
              onChange={(e) => {
                const id = e.target.value ? Number(e.target.value) : undefined;
                const chosen = props.layers.find((l) => l.id === id);
                props.onChange({
                  target_layer: id,
                  new_layer: id ? undefined : { name: layer.name, domain: "other", geometry_type: family },
                  fields: layer.fields.map((f) => ({
                    source: f.name,
                    target: chosen ? (chosen.schema.find((s) => s.name === f.suggested_name.toLowerCase())?.name ?? "") : f.suggested_name.toLowerCase(),
                    type: f.type,
                  })),
                });
              }}
            >
              <option value="">A new layer</option>
              {props.layers
                .filter((l) => l.geometry_type === family)
                .map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.name} ({l.crs_detail.code})
                  </option>
                ))}
            </select>
          </label>
          {plan.new_layer && (
            <div className="inline-form">
              <input
                aria-label={`New layer name for ${layer.name}`}
                value={plan.new_layer.name}
                onChange={(e) => props.onChange({ new_layer: { ...plan.new_layer!, name: e.target.value } })}
              />
              <select
                aria-label={`Domain for ${layer.name}`}
                value={plan.new_layer.domain}
                onChange={(e) => props.onChange({ new_layer: { ...plan.new_layer!, domain: e.target.value as Domain } })}
              >
                {Object.entries(DOMAIN_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
              <span className="muted small">
                keeps the file's coordinate system ({plan.crs || "?"})
              </span>
            </div>
          )}
          {target && plan.crs && target.crs_detail.code !== plan.crs && (
            <p className="muted small">
              Coordinates will be converted from {plan.crs} to {target.crs_detail.code}; the report names the transformation
              and its accuracy.
            </p>
          )}
          <table className="data">
            <thead>
              <tr>
                <th>Field in the file</th>
                <th>Becomes</th>
              </tr>
            </thead>
            <tbody>
              {plan.fields.map((f, j) => (
                <tr key={f.source}>
                  <td>{f.source}</td>
                  <td>
                    {target ? (
                      <select
                        aria-label={`Target field for ${f.source}`}
                        value={f.target}
                        onChange={(e) =>
                          props.onChange({ fields: plan.fields.map((g, k) => (k === j ? { ...g, target: e.target.value } : g)) })
                        }
                      >
                        <option value="">(don't import)</option>
                        {target.schema.map((s) => (
                          <option key={s.name} value={s.name}>
                            {s.label}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <input
                        aria-label={`New field name for ${f.source}`}
                        value={f.target}
                        onChange={(e) =>
                          props.onChange({ fields: plan.fields.map((g, k) => (k === j ? { ...g, target: e.target.value } : g)) })
                        }
                      />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="inline-form">
            <label>
              Invalid shapes
              <select
                value={plan.invalid_geometry}
                onChange={(e) => props.onChange({ invalid_geometry: e.target.value as ImportPlanItem["invalid_geometry"] })}
              >
                <option value="skip">Skip them</option>
                <option value="fix">Try to repair them</option>
                <option value="abort">Stop the import</option>
              </select>
            </label>
            <label>
              Duplicates
              <select value={plan.duplicates} onChange={(e) => props.onChange({ duplicates: e.target.value as ImportPlanItem["duplicates"] })}>
                <option value="keep">Keep them</option>
                <option value="skip">Skip them</option>
              </select>
            </label>
            <label>
              Values that don't fit a field
              <select value={plan.bad_values} onChange={(e) => props.onChange({ bad_values: e.target.value as ImportPlanItem["bad_values"] })}>
                <option value="blank">Leave empty</option>
                <option value="skip_feature">Skip the feature</option>
              </select>
            </label>
          </div>
          {problem && <p className="error small">{problem}</p>}
        </div>
      )}
    </fieldset>
  );
}

