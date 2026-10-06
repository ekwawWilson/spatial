import type { SyncConflictDetail } from "@spatial/map-core";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ErrorMessage } from "../components/ErrorMessage";
import { useLoad } from "../components/useLoad";
import { useSession } from "../session";

function show(value: unknown): string {
  return value === null || value === undefined || value === "" ? "—" : String(value);
}

/** Field edits that were based on an older version than the office's, side by
 * side, for a person to settle. */
export function ConflictsPage() {
  const { projectId } = useParams();
  const id = Number(projectId);
  const { api, can, districtId } = useSession();
  const list = useLoad(() => api.listConflicts(id, "open"), [api, id, districtId]);
  const [openId, setOpenId] = useState<number | null>(null);
  const [detail, setDetail] = useState<SyncConflictDetail | null>(null);
  const [choice, setChoice] = useState<Record<string, "office" | "field">>({});
  const [fieldShape, setFieldShape] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [done, setDone] = useState<string | null>(null);
  const canResolve = can("sync.resolve");

  useEffect(() => {
    setDetail(null);
    setChoice({});
    setFieldShape(false);
    if (openId === null) return;
    let current = true;
    api
      .getConflict(openId)
      .then((d) => current && setDetail(d))
      .catch((err: unknown) => current && setError(err));
    return () => {
      current = false;
    };
  }, [api, openId]);

  async function resolve(resolution: "keep_office" | "keep_field" | "merged") {
    if (!detail) return;
    setError(null);
    try {
      if (resolution === "merged") {
        const properties: Record<string, unknown> = {};
        for (const field of detail.schema) {
          const from = choice[field.name] ?? "office";
          const source = from === "field" ? (detail.field.properties ?? {}) : detail.office.properties;
          if (field.name in source) properties[field.name] = source[field.name];
        }
        await api.resolveConflict(detail.id, { resolution, properties, use_field_geometry: fieldShape });
      } else {
        await api.resolveConflict(detail.id, { resolution });
      }
      setDone(
        resolution === "keep_office" ? "Kept the office version." : resolution === "keep_field" ? "Kept the field version." : "Saved the merged version.",
      );
      setOpenId(null);
      list.reload();
    } catch (err) {
      setError(err);
    }
  }

  const fieldProps = detail?.field.properties ?? null;

  return (
    <section className="page">
      <p>
        <Link to={`/projects/${id}`}>← Back to the project</Link>
      </p>
      <h1>Field conflicts</h1>
      <p className="muted">
        A conflict is a change made in the field on a version of a feature that the office had already changed. Nothing is lost:
        choose which to keep, or take some values from each.
      </p>
      <ErrorMessage error={error ?? list.error} />
      {done && <p role="status">{done}</p>}
      {list.data?.length === 0 && <p>No conflicts waiting.</p>}
      {list.data && list.data.length > 0 && (
        <table className="data">
          <thead>
            <tr>
              <th>Layer</th>
              <th>Feature</th>
              <th>From the field</th>
              <th>Versions</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {list.data.map((c) => (
              <tr key={c.id}>
                <td>{c.layer_name}</td>
                <td>#{c.feature}</td>
                <td>
                  {c.submitted_by ?? "—"} · {new Date(c.created_at).toLocaleString()}
                </td>
                <td>
                  edited version {c.base_version}; office was at {c.server_version}
                </td>
                <td>
                  <button type="button" className="link" aria-expanded={openId === c.id} onClick={() => setOpenId(openId === c.id ? null : c.id)}>
                    {openId === c.id ? "Close" : "Compare"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {detail && (
        <section aria-label="Compare versions" className="card wide">
          <h2>
            {detail.layer_name} #{detail.feature}
          </h2>
          <table className="data">
            <thead>
              <tr>
                <th>Field</th>
                <th>Office (version {detail.office.version})</th>
                <th>Field ({detail.submitted_by ?? "device"})</th>
              </tr>
            </thead>
            <tbody>
              {detail.schema.map((field) => {
                const office = detail.office.properties[field.name];
                const sent = fieldProps !== null && field.name in fieldProps;
                const fromField = sent ? fieldProps![field.name] : office;
                const differs = sent && show(office) !== show(fromField);
                return (
                  <tr key={field.name} className={differs ? "differs" : ""}>
                    <td>{field.label}</td>
                    <td>
                      <label className="checkbox">
                        {differs && canResolve && (
                          <input type="radio" name={`pick-${field.name}`} aria-label={`Office value for ${field.label}`} checked={(choice[field.name] ?? "office") === "office"} onChange={() => setChoice({ ...choice, [field.name]: "office" })} />
                        )}
                        {show(office)}
                      </label>
                    </td>
                    <td>
                      <label className="checkbox">
                        {differs && canResolve && (
                          <input type="radio" name={`pick-${field.name}`} aria-label={`Field value for ${field.label}`} checked={choice[field.name] === "field"} onChange={() => setChoice({ ...choice, [field.name]: "field" })} />
                        )}
                        {differs ? <strong>{show(fromField)}</strong> : "same"}
                      </label>
                    </td>
                  </tr>
                );
              })}
              <tr className={detail.field.geometry ? "differs" : ""}>
                <td>Shape</td>
                <td>as in the office</td>
                <td>
                  {detail.field.geometry ? (
                    <label className="checkbox">
                      {canResolve && <input type="checkbox" aria-label="Use the shape from the field" checked={fieldShape} onChange={(e) => setFieldShape(e.target.checked)} />}
                      <strong>changed in the field</strong>
                    </label>
                  ) : (
                    "not changed"
                  )}
                </td>
              </tr>
            </tbody>
          </table>
          {detail.field.capture.accuracy_m !== undefined && detail.field.capture.accuracy_m !== null && (
            <p className="muted small">Field GPS accuracy ±{detail.field.capture.accuracy_m.toFixed(1)} m.</p>
          )}
          {canResolve ? (
            <div className="inline-form">
              <button type="button" className="secondary" onClick={() => resolve("keep_office")}>
                Keep the office version
              </button>
              <button type="button" className="secondary" onClick={() => resolve("keep_field")}>
                Keep the field version
              </button>
              <button type="button" onClick={() => resolve("merged")}>
                Save the values picked above
              </button>
            </div>
          ) : (
            <p className="muted">Planners and district administrators resolve conflicts.</p>
          )}
        </section>
      )}
    </section>
  );
}
