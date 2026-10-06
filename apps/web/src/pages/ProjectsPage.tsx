import type { SppReport } from "@spatial/map-core";
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import { ErrorMessage } from "../components/ErrorMessage";
import { useLoad } from "../components/useLoad";
import { useSession } from "../session";

export function ProjectsPage() {
  const { api, districtId, can } = useSession();
  const projects = useLoad(() => api.listProjects(), [api, districtId]);
  const defaults = useLoad(() => api.crsDefaults(), [api, districtId]);
  const systems = useLoad(() => api.listCrs(), [api, districtId]);
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [community, setCommunity] = useState("");
  const [crs, setCrs] = useState<number | "">("");
  const [error, setError] = useState<unknown>(null);
  const [opening, setOpening] = useState(false);
  const [openError, setOpenError] = useState<unknown>(null);
  const [opened, setOpened] = useState<SppReport | null>(null);

  async function openFile(file: File) {
    setOpening(true);
    setOpenError(null);
    setOpened(null);
    try {
      setOpened(await api.openProjectFile(file));
      projects.reload();
    } catch (err) {
      setOpenError(err);
    } finally {
      setOpening(false);
    }
  }

  async function create(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const project = await api.createProject({ name, community, ...(crs ? { crs } : {}) });
      navigate(`/projects/${project.id}`);
    } catch (err) {
      setError(err);
    }
  }

  return (
    <section className="page">
      <h1>Plan projects</h1>
      <ErrorMessage error={projects.error} />
      <table className="data">
        <thead>
          <tr>
            <th>Project</th>
            <th>Community</th>
            <th>Coordinate system</th>
            <th>Layers</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {projects.data?.results.map((p) => (
            <tr key={p.id}>
              <td>
                <Link to={`/projects/${p.id}`}>{p.name}</Link>
              </td>
              <td>{p.community}</td>
              <td>{p.crs_detail.code}</td>
              <td>{p.layer_count}</td>
              <td>{p.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {projects.data?.results.length === 0 && <p className="muted">No projects yet.</p>}

      {can("project.edit") && can("data.import") && (
        <section className="card wide" aria-label="Open a project file">
          <h2>Open a project file (.spp)</h2>
          <p className="muted small">
            A project saved from this platform, here or on another server that shares this organisation's key. It opens as
            a new project in this district; nothing existing is changed.
          </p>
          <input
            type="file"
            accept=".spp"
            aria-label="Project file"
            disabled={opening}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void openFile(file);
              e.target.value = "";
            }}
          />
          {opening && <p role="status">Opening the file…</p>}
          <ErrorMessage error={openError} />
          {opened && (
            <div role="status" aria-label="Opened project">
              <p>
                Opened <Link to={`/projects/${opened.project}`}>{opened.name}</Link>: {opened.layers} layer
                {opened.layers === 1 ? "" : "s"}, {opened.features} features, {opened.checklist_items} checklist items,{" "}
                {opened.attachments} document{opened.attachments === 1 ? "" : "s"}.
              </p>
              <ul className="small">
                {opened.renamed_from && (
                  <li>
                    A project called "{opened.renamed_from}" already exists here, so this copy is named "{opened.name}".
                  </li>
                )}
                {opened.from_district && (
                  <li>
                    Saved{opened.saved_by ? ` by ${opened.saved_by}` : ""} in {opened.from_district}
                    {opened.saved_at ? ` on ${opened.saved_at.slice(0, 10)}` : ""}.
                  </li>
                )}
                {opened.crs_added.map((c) => (
                  <li key={c}>Added the coordinate system {c} to this district.</li>
                ))}
                {opened.basemaps_added.map((b) => (
                  <li key={b}>Added the basemap {b}.</li>
                ))}
                {opened.basemaps_skipped.length > 0 && (
                  <li>
                    Basemaps not added (a district administrator can add them): {opened.basemaps_skipped.join(", ")}.
                  </li>
                )}
              </ul>
            </div>
          )}
        </section>
      )}

      {can("project.edit") && (
        <form className="card wide" onSubmit={create} aria-label="New project">
          <h2>New project</h2>
          <label>
            Name
            <input required value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Kasoa central local plan" />
          </label>
          <label>
            Community
            <input value={community} onChange={(e) => setCommunity(e.target.value)} />
          </label>
          <label>
            Coordinate system
            <select aria-label="Coordinate system" value={crs} onChange={(e) => setCrs(e.target.value ? Number(e.target.value) : "")}>
              <option value="">
                Default{defaults.data ? `: ${defaults.data.effective.crs.code} (${defaults.data.effective.source} default)` : ""}
              </option>
              {systems.data?.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.code} · {s.name}
                </option>
              ))}
            </select>
          </label>
          <p className="muted">The coordinate system is fixed once the project is created.</p>
          <ErrorMessage error={error} />
          <button type="submit">Create project</button>
        </form>
      )}
    </section>
  );
}
