import type { ContourResult, CoordinateSystem, Imagery } from "@spatial/map-core";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ErrorMessage } from "../components/ErrorMessage";
import { useLoad } from "../components/useLoad";
import { useSession } from "../session";

function size(bytes: number): string {
  return bytes >= 1024 ** 3 ? `${(bytes / 1024 ** 3).toFixed(1)} GB` : `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}

function pixel(metres: number | null): string {
  if (metres === null) return "—";
  return metres < 1 ? `${(metres * 100).toFixed(1)} cm` : `${metres.toFixed(2)} m`;
}

const STATUS = { queued: "Waiting", processing: "Processing…", ready: "Ready", failed: "Failed" };

/** Drone orthophotos and elevation models of a project. */
export function ImageryPage() {
  const { projectId } = useParams();
  const id = Number(projectId);
  const { api, can, districtId } = useSession();
  const list = useLoad(() => api.listImagery(id), [api, id, districtId]);
  const systems = useLoad(() => api.listCrs(), [api, districtId]);
  const [error, setError] = useState<unknown>(null);
  const [note, setNote] = useState<string | null>(null);
  const canEdit = can("data.import");

  // Keep checking while something is being processed.
  const working = list.data?.some((i) => i.status === "queued" || i.status === "processing") ?? false;
  const reload = list.reload;
  useEffect(() => {
    if (!working) return;
    const timer = setInterval(reload, 3000);
    return () => clearInterval(timer);
  }, [working, reload]);

  async function run(action: () => Promise<unknown>, done?: string) {
    setError(null);
    setNote(null);
    try {
      await action();
      if (done) setNote(done);
      list.reload();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <section className="page">
      <p>
        <Link to={`/projects/${id}`}>← Back to the project</Link>
      </p>
      <h1>Imagery</h1>
      <p className="muted">
        Upload the Assembly's own drone or satellite images (GeoTIFF). An orthophoto appears in the project's basemap list and can
        be taken into the field offline. An elevation model can be turned into contour lines.
      </p>
      <ErrorMessage error={error ?? list.error} />
      {note && <p role="status">{note}</p>}

      {list.data?.length === 0 && <p>No imagery yet.</p>}
      {list.data && list.data.length > 0 && (
        <table className="data">
          <thead>
            <tr>
              <th>Name</th>
              <th>Kind</th>
              <th>Status</th>
              <th>Captured</th>
              <th>Pixel size</th>
              <th>Coordinate system</th>
              <th>Size</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {list.data.map((image) => (
              <ImageryRow key={image.id} image={image} canEdit={canEdit} canContour={canEdit && can("layer.edit")} run={run} />
            ))}
          </tbody>
        </table>
      )}

      {canEdit && <UploadForm projectId={id} systems={systems.data ?? []} onUploaded={() => run(async () => undefined, "Uploaded. It is being checked and converted.")} onError={setError} />}
    </section>
  );
}

function ImageryRow(props: { image: Imagery; canEdit: boolean; canContour: boolean; run(action: () => Promise<unknown>, done?: string): Promise<void> }) {
  const { api } = useSession();
  const navigate = useNavigate();
  const { image } = props;
  const [date, setDate] = useState(image.capture_date ?? "");
  const [interval, setIntervalValue] = useState("1");
  useEffect(() => setDate(image.capture_date ?? ""), [image.capture_date]);

  return (
    <tr>
      <td>
        {image.name}
        {image.source && <div className="muted small">{image.source}</div>}
        {image.status === "failed" && (
          <div role="alert" className="error small">
            {image.error}
          </div>
        )}
      </td>
      <td>{image.kind === "dem" ? "Elevation model" : "Orthophoto"}</td>
      <td>{STATUS[image.status]}</td>
      <td>
        {props.canEdit && image.status === "ready" ? (
          <input
            type="date"
            aria-label={`Capture date of ${image.name}`}
            value={date}
            onChange={(e) => setDate(e.target.value)}
            onBlur={() => date !== (image.capture_date ?? "") && props.run(() => api.updateImagery(image.id, { capture_date: date || null }), "Capture date saved.")}
          />
        ) : (
          (image.capture_date ?? "—")
        )}
      </td>
      <td>{pixel(image.resolution_m)}</td>
      <td className="small">{image.crs || "—"}</td>
      <td>{image.size_bytes ? size(image.size_bytes) : "—"}</td>
      <td>
        {image.status === "ready" && image.basemap !== null && image.bounds && (
          <button
            type="button"
            className="secondary"
            onClick={() => navigate(`/projects/${image.project}`, { state: { showImagery: { basemap: image.basemap, bounds: image.bounds } } })}
          >
            Show on map
          </button>
        )}
        {props.canContour && image.kind === "dem" && image.status === "ready" && (
          <span className="inline-form">
            <input
              type="number"
              min={0.01}
              step="any"
              style={{ width: "5rem" }}
              aria-label={`Contour interval for ${image.name}`}
              value={interval}
              onChange={(e) => setIntervalValue(e.target.value)}
            />
            <button
              type="button"
              className="secondary"
              onClick={() =>
                props.run(async () => {
                  const result: ContourResult = await api.makeContours(image.id, Number(interval));
                  return result;
                }, `Contours made in the layer "Topography (contours)".`)
              }
            >
              Make contours
            </button>
          </span>
        )}
        {props.canEdit && (
          <button
            type="button"
            className="link"
            aria-label={`Delete ${image.name}`}
            onClick={() => window.confirm(`Delete "${image.name}"? Its basemap is switched off too.`) && props.run(() => api.deleteImagery(image.id), "Deleted.")}
          >
            Delete
          </button>
        )}
      </td>
    </tr>
  );
}

function UploadForm(props: { projectId: number; systems: CoordinateSystem[]; onUploaded(): void; onError(error: unknown): void }) {
  const { api } = useSession();
  const [file, setFile] = useState<File | null>(null);
  const [kind, setKind] = useState<"ortho" | "dem">("ortho");
  const [name, setName] = useState("");
  const [captureDate, setCaptureDate] = useState("");
  const [source, setSource] = useState("");
  const [crs, setCrs] = useState("");
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(0);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    props.onError(null);
    try {
      setProgress(0);
      await api.uploadImagery({ project: props.projectId, file, kind, name, capture_date: captureDate, source, crs }, setProgress);
      setFile(null);
      setName("");
      (event.target as HTMLFormElement).reset();
      props.onUploaded();
    } catch (err) {
      props.onError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card wide stack" aria-label="Upload imagery" onSubmit={submit}>
      <h2>Upload imagery</h2>
      <label>
        GeoTIFF file (.tif)
        <input type="file" accept=".tif,.tiff" aria-label="GeoTIFF file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </label>
      <div className="inline-form">
        <label>
          Kind
          <select aria-label="Kind" value={kind} onChange={(e) => setKind(e.target.value as "ortho" | "dem")}>
            <option value="ortho">Orthophoto (drone or satellite image)</option>
            <option value="dem">Elevation model (for contours)</option>
          </select>
        </label>
        <label>
          Name
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Kasoa drone flight" />
        </label>
        <label>
          Captured on
          <input type="date" aria-label="Captured on" value={captureDate} onChange={(e) => setCaptureDate(e.target.value)} />
        </label>
        <label>
          Captured by
          <input value={source} onChange={(e) => setSource(e.target.value)} placeholder="e.g. Assembly drone team" />
        </label>
      </div>
      <label>
        Coordinate system (only if the file doesn't say)
        <select aria-label="Coordinate system if the file has none" value={crs} onChange={(e) => setCrs(e.target.value)}>
          <option value="">Read it from the file</option>
          {props.systems
            .filter((s) => s.code.startsWith("EPSG:"))
            .map((s) => (
              <option key={s.code} value={s.code}>
                {s.code} · {s.name}
              </option>
            ))}
        </select>
      </label>
      <p className="muted small">
        Up to 500 MB. Large files are sent in pieces: keep this page open until the upload finishes. If the connection drops, the upload
        carries on by itself. The capture date feeds the readiness checklist's "recent imagery" item.
      </p>
      <div className="inline-form">
        <button type="submit" disabled={!file || busy}>
          {busy ? "Uploading…" : "Upload"}
        </button>
        {busy && (
          <>
            <progress aria-label="Upload progress" max={1} value={progress} />
            <span role="status">{Math.floor(progress * 100)}%</span>
          </>
        )}
      </div>
    </form>
  );
}
