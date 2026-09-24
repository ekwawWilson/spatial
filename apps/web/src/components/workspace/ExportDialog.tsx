import type { CoordinateSystem, DataJob, ExportFormat, Layer } from "@spatial/map-core";
import { useEffect, useState, type FormEvent } from "react";

import { useSession } from "../../session";
import { ErrorMessage } from "../ErrorMessage";

const FORMATS: { value: ExportFormat; label: string; note?: string }[] = [
  { value: "gpkg", label: "GeoPackage (.gpkg)" },
  { value: "shp", label: "Shapefile (zipped)", note: "Field names are cut to 10 characters; a CSV lists the full names." },
  { value: "geojson", label: "GeoJSON" },
  { value: "kml", label: "KML (Google Earth)", note: "Always WGS 84." },
  { value: "kmz", label: "KMZ (Google Earth)", note: "Always WGS 84." },
  { value: "dxf", label: "DXF (CAD)", note: "Geometry and layer names only." },
  { value: "dwg", label: "DWG (CAD, experimental)", note: "Geometry and layer names only; only if the server supports DWG." },
];

export function saveBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function ExportDialog(props: {
  projectId: number;
  layers: Layer[];
  systems: CoordinateSystem[];
  selection?: { layerId: number; featureIds: number[] } | null;
  onClose(): void;
}) {
  const { api } = useSession();
  const [layerIds, setLayerIds] = useState<number[]>(props.layers.filter((l) => l.visible).map((l) => l.id));
  const [format, setFormat] = useState<ExportFormat>("gpkg");
  const [crs, setCrs] = useState("");
  const [onlySelection, setOnlySelection] = useState(false);
  const [job, setJob] = useState<DataJob | null>(null);
  const [error, setError] = useState<unknown>(null);
  const wgs84Only = format === "kml" || format === "kmz";

  async function start(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const selection = onlySelection && props.selection ? props.selection : null;
      setJob(
        await api.startExport({
          project: props.projectId,
          layer_ids: selection ? [selection.layerId] : layerIds,
          format,
          crs: wgs84Only ? null : crs || null,
          feature_ids: selection?.featureIds,
        }),
      );
    } catch (err) {
      setError(err);
    }
  }

  useEffect(() => {
    if (!job || !["queued", "running"].includes(job.status)) return;
    const timer = setTimeout(async () => {
      try {
        const next = await api.getJob(job.id);
        setJob(next);
        if (next.status === "done") saveBlob(await api.downloadExport(next), next.result_name);
      } catch (err) {
        setError(err);
      }
    }, 1000);
    return () => clearTimeout(timer);
  }, [api, job]);

  return (
    <form className="card wide" role="dialog" aria-modal="true" aria-label="Export data" onSubmit={start}>
      <h2>Export data</h2>
      {!job && (
        <>
          <fieldset>
            <legend>Layers</legend>
            {props.layers.map((l) => (
              <label key={l.id} className="checkbox">
                <input
                  type="checkbox"
                  checked={layerIds.includes(l.id)}
                  disabled={onlySelection}
                  onChange={(e) => setLayerIds(e.target.checked ? [...layerIds, l.id] : layerIds.filter((id) => id !== l.id))}
                />
                {l.name} ({l.feature_count})
              </label>
            ))}
            {props.selection && props.selection.featureIds.length > 0 && (
              <label className="checkbox">
                <input type="checkbox" checked={onlySelection} onChange={(e) => setOnlySelection(e.target.checked)} />
                Only the selected feature(s)
              </label>
            )}
          </fieldset>
          <label>
            Format
            <select aria-label="Format" value={format} onChange={(e) => setFormat(e.target.value as ExportFormat)}>
              {FORMATS.map((f) => (
                <option key={f.value} value={f.value}>
                  {f.label}
                </option>
              ))}
            </select>
          </label>
          {FORMATS.find((f) => f.value === format)?.note && <p className="muted small">{FORMATS.find((f) => f.value === format)!.note}</p>}
          <label>
            Coordinate system
            <select aria-label="Export coordinate system" value={wgs84Only ? "EPSG:4326" : crs} disabled={wgs84Only} onChange={(e) => setCrs(e.target.value)}>
              <option value="">Each layer's own (no conversion)</option>
              {props.systems.map((s) => (
                <option key={s.code} value={s.code}>
                  {s.code} · {s.name}
                </option>
              ))}
            </select>
          </label>
          <ErrorMessage error={error} />
          <div className="inline-form">
            <button type="submit" disabled={!onlySelection && layerIds.length === 0}>
              Export
            </button>
            <button type="button" className="link" onClick={props.onClose}>
              Cancel
            </button>
          </div>
        </>
      )}
      {job && ["queued", "running"].includes(job.status) && <p role="status">Preparing the export…</p>}
      {job?.status === "done" && (
        <div className="stack">
          <p role="status">Export ready: {job.result_name}</p>
          <button type="button" onClick={async () => saveBlob(await api.downloadExport(job), job.result_name)}>
            Download again
          </button>
          <button type="button" className="link" onClick={props.onClose}>
            Close
          </button>
        </div>
      )}
      {job?.status === "failed" && (
        <p role="alert" className="error">
          The export failed: {job.error}
        </p>
      )}
    </form>
  );
}
