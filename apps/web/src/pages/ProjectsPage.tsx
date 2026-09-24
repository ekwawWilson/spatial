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
