import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { ErrorMessage } from "../components/ErrorMessage";
import { useLoad } from "../components/useLoad";
import { saveBlob } from "../components/workspace/ExportDialog";
import { useSession } from "../session";

const SCALES = [500, 1000, 1250, 2500, 5000, 10000, 25000, 50000];

/** Prints the project as a plan sheet: a PDF at a true scale in the project's grid. */
export function PlanSheetPage() {
  const { projectId } = useParams();
  const id = Number(projectId);
  const { api, districtId } = useSession();
  const project = useLoad(() => api.getProject(id), [api, id, districtId]);
  const [paper, setPaper] = useState("A3");
  const [scale, setScale] = useState("");
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [note, setNote] = useState<string | null>(null);

  async function print(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setNote(null);
    setBusy(true);
    try {
      const sheet = await api.planSheet(id, { paper, scale: scale ? Number(scale) : undefined, title: title || undefined });
      saveBlob(sheet.blob, `${(title || project.data?.name || "plan").replace(/[^\w-]+/g, "-")}-${paper}.pdf`);
      setNote(`Drawn at 1:${sheet.scale.toLocaleString("en-GB")} on ${paper}. Print it at 100% ("actual size"), not "fit to page", or the scale is lost.`);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="page">
      <p>
        <Link to={`/projects/${id}`}>← Back to the project</Link>
      </p>
      <h1>Plan sheet</h1>
      <p className="muted">
        The project's visible layers as a PDF at a true scale in its own coordinate system
        {project.data && ` (${project.data.crs_detail.code} ${project.data.crs_detail.name})`}, with a title block, legend, grid
        coordinates, scale bar and north arrow. It shows the planning area if the project has one, otherwise everything in its layers.
      </p>
      <ErrorMessage error={error ?? project.error} />
      {note && <p role="status">{note}</p>}
      <form className="card wide stack" aria-label="Plan sheet" onSubmit={print}>
        <div className="inline-form">
          <label>
            Paper (landscape)
            <select aria-label="Paper" value={paper} onChange={(e) => setPaper(e.target.value)}>
              {["A4", "A3", "A2", "A1"].map((size) => (
                <option key={size} value={size}>
                  {size}
                </option>
              ))}
            </select>
          </label>
          <label>
            Scale
            <select aria-label="Scale" value={scale} onChange={(e) => setScale(e.target.value)}>
              <option value="">The largest that fits</option>
              {SCALES.map((s) => (
                <option key={s} value={s}>
                  1:{s.toLocaleString("en-GB")}
                </option>
              ))}
            </select>
          </label>
          <label>
            Title
            <input aria-label="Title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder={project.data?.name ?? ""} />
          </label>
        </div>
        <p className="muted small">
          Layers are drawn in their order and styles from the project's map; switch a layer off there to leave it out. Labels follow each
          layer's label setting. Basemaps and imagery are not printed.
        </p>
        <div className="inline-form">
          <button type="submit" disabled={busy}>
            {busy ? "Drawing…" : "Download the plan sheet"}
          </button>
        </div>
      </form>
    </section>
  );
}
