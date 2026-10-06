import type { DevelopmentStandard, Layer, LayerRoleRow, LinkCounts, RelationsRegistry, RelationsTotals, RelationshipLink } from "@spatial/map-core";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ErrorMessage } from "../components/ErrorMessage";
import { useLoad } from "../components/useLoad";
import { useSession } from "../session";

const RULES: Record<string, string> = {
  setback: "Too close to the plot boundary",
  floors: "Too many floors",
  coverage: "Plot coverage too high",
  plot_size: "Plot too small",
  no_permit: "No permit",
  flood_area: "Built in a flood-prone area",
};

const METHODS = { calculated: "Calculated", inferred: "Inferred", confirmed: "Confirmed by a person" };

export function describeLink(link: RelationshipLink): string {
  const d = link.details as Record<string, number | string | boolean | null>;
  if (link.type === "violates") {
    const parts = [RULES[link.rule] ?? link.rule];
    if (d.measured_m !== undefined) parts.push(`${d.measured_m} m, needs ${d.required_m} m`);
    if (d.measured_pct !== undefined) parts.push(`${d.measured_pct}%, limit ${d.allowed_pct}%`);
    if (d.measured !== undefined) parts.push(`${d.measured}, limit ${d.allowed}`);
    if (d.measured_m2 !== undefined) parts.push(`${d.measured_m2} m², needs ${d.required_m2} m²`);
    return `${parts.join(": ")} (${d.zone} standard)`;
  }
  const parts: string[] = [];
  if (typeof d.distance_m === "number") parts.push(`${d.distance_m} m away`);
  if (typeof d.share === "number" && d.share < 0.995) parts.push(`${Math.round(d.share * 100)}% of it`);
  if (d.risk) parts.push(`risk: ${d.risk}`);
  if (d.matched_by) parts.push(d.matched_by === "id" ? "matched by its id" : "matched by where it is");
  if (d.status) parts.push(`status: ${d.status}`);
  if (typeof d.population === "number") parts.push(`population ${d.population.toLocaleString("en-GB")}`);
  return parts.join(" · ");
}

function Totals({ totals }: { totals: RelationsTotals }) {
  const rows: [string, number | undefined][] = [
    ["Properties", totals.properties],
    ["In a flood-prone area", totals.in_flood_area],
    ["Without road access", totals.without_road_access],
    ["With no drain nearby", totals.without_drain],
    ["With a permit", totals.with_permit],
    ["Breaking a standard", totals.with_violations],
    ["In no community", totals.in_no_community],
    ["Population served by facilities", totals.population_served],
    ["Needs addressed by projects", totals.needs === undefined ? undefined : totals.needs_addressed],
  ];
  return (
    <dl className="facts">
      {rows
        .filter(([, value]) => value !== undefined)
        .map(([label, value]) => (
          <div key={label} style={{ display: "contents" }}>
            <dt>{label}</dt>
            <dd>
              {value!.toLocaleString("en-GB")}
              {label.startsWith("Needs") ? ` of ${totals.needs}` : ""}
            </dd>
          </div>
        ))}
    </dl>
  );
}

/** How the project's features relate: which layers play which part, the
 * procedures that work the links out, and the links people need to check. */
export function RelationsPage() {
  const { projectId } = useParams();
  const id = Number(projectId);
  const { api, can, districtId } = useSession();
  const registry = useLoad(() => api.relationsRegistry(), [api]);
  const layers = useLoad(() => api.listLayers(id), [api, id, districtId]);
  const roles = useLoad(() => api.getLayerRoles(id), [api, id, districtId]);
  const run = useLoad(() => api.latestRelationsRun(id), [api, id, districtId]);
  const [type, setType] = useState("violates");
  const [onlyInferred, setOnlyInferred] = useState(false);
  const links = useLoad(
    () => api.listRelationships({ project: id, type, method: onlyInferred ? "inferred" : undefined }),
    [api, id, districtId, type, onlyInferred, run.data?.latest?.id],
  );
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const canEdit = can("relations.edit");

  async function act(action: () => Promise<unknown>, after: () => void) {
    setError(null);
    try {
      await action();
      after();
    } catch (err) {
      setError(err);
    }
  }

  async function runNow() {
    setBusy(true);
    await act(
      () => api.runRelations(id),
      () => run.reload(),
    );
    setBusy(false);
  }

  const latest = run.data?.latest ?? null;
  const summary = run.data?.summary ?? null;
  const anySet = roles.data?.roles.some((r) => r.layer !== null) ?? false;

  return (
    <section className="page">
      <p>
        <Link to={`/projects/${id}`}>← Back to the project</Link>
      </p>
      <h1>Relationships</h1>
      <p className="muted">
        The platform works out how features relate: which street and community a property is on, whether it floods, which drain and
        permit it has, and whether it breaks the district's standards. First say which layer holds what.
      </p>
      <ErrorMessage error={error ?? roles.error ?? run.error} />

      {registry.data && roles.data && layers.data && (
        <RolesForm
          key={JSON.stringify(roles.data.roles.map((r) => [r.role, r.layer]))}
          registry={registry.data}
          rows={roles.data.roles}
          layers={layers.data}
          canEdit={canEdit}
          onSave={(next) => act(() => api.setLayerRoles(id, next), roles.reload)}
        />
      )}

      <section aria-label="Run" className="card wide">
        <h2>Work out the relationships</h2>
        <div className="inline-form">
          {canEdit && (
            <button type="button" onClick={runNow} disabled={busy || !anySet}>
              {busy ? "Running…" : "Run now"}
            </button>
          )}
          <span className="muted small">
            {latest
              ? `Last run ${new Date(latest.started_at).toLocaleString()} (${latest.trigger === "manual" ? `by ${latest.started_by ?? "someone"}` : latest.trigger === "nightly" ? "nightly" : "after an edit"}): ${latest.status}`
              : "Not run yet."}{" "}
            It also runs every night, and after edits.
          </span>
        </div>
        {latest?.status === "failed" && (
          <p role="alert" className="error">
            The last run failed and changed nothing: {latest.error}
          </p>
        )}
        {latest && registry.data && (
          <table className="data">
            <thead>
              <tr>
                <th>Step</th>
                <th>Result of the last run</th>
              </tr>
            </thead>
            <tbody>
              {registry.data.procedures
                .filter((p) => p.code !== "aggregation")
                .map((p) => {
                  const result = latest.report[p.code] as Record<string, unknown> | undefined;
                  return (
                    <tr key={p.code}>
                      <td>{p.does}</td>
                      <td className="small">
                        {!result
                          ? "—"
                          : typeof result.skipped === "string"
                            ? `Skipped. ${result.skipped}`
                            : Object.entries(result as Record<string, LinkCounts>)
                                .map(([code, c]) => `${registry.data!.link_types.find((t) => t.code === code)?.verb ?? code}: ${c.found} found${c.added ? `, ${c.added} new` : ""}${c.removed ? `, ${c.removed} removed` : ""}${c.kept ? `, ${c.kept} decided by people` : ""}`)
                                .join("; ") || "Nothing found"}
                      </td>
                    </tr>
                  );
                })}
            </tbody>
          </table>
        )}
      </section>

      {summary && (
        <section aria-label="Totals" className="card wide">
          <h2>Totals</h2>
          <Totals totals={summary.project} />
          {summary.communities.length > 0 && (
            <table className="data">
              <thead>
                <tr>
                  <th>Community</th>
                  <th>Properties</th>
                  <th>Flood-prone</th>
                  <th>No road access</th>
                  <th>No drain nearby</th>
                  <th>Breaking a standard</th>
                  <th>Facilities</th>
                </tr>
              </thead>
              <tbody>
                {summary.communities.map((c) => (
                  <tr key={c.feature}>
                    <td>{c.name}</td>
                    <td>{c.properties}</td>
                    <td>{c.in_flood_area ?? "—"}</td>
                    <td>{c.without_road_access ?? "—"}</td>
                    <td>{c.without_drain ?? "—"}</td>
                    <td>{c.with_violations ?? "—"}</td>
                    <td>{c.facilities ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}

      {registry.data && (
        <section aria-label="Links" className="card wide">
          <h2>Links</h2>
          <div className="inline-form">
            <label>
              Show
              <select aria-label="Kind of link" value={type} onChange={(e) => setType(e.target.value)}>
                {registry.data.link_types.map((t) => (
                  <option key={t.code} value={t.code}>
                    {registry.data!.roles.find((r) => r.code === t.subject)?.label ?? t.subject} {t.verb}{" "}
                    {t.object ? registry.data!.roles.find((r) => r.code === t.object)?.label : "a planning standard"}
                  </option>
                ))}
              </select>
            </label>
            <label className="checkbox">
              <input type="checkbox" checked={onlyInferred} onChange={(e) => setOnlyInferred(e.target.checked)} /> Only those to check
              (inferred)
            </label>
          </div>
          {links.data?.results.length === 0 && <p className="muted">None.</p>}
          {links.data && links.data.results.length > 0 && (
            <table className="data">
              <thead>
                <tr>
                  <th>From</th>
                  <th>To</th>
                  <th>How it was made</th>
                  <th>Details</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {links.data.results.map((link) => (
                  <tr key={link.id} className={link.status === "rejected" ? "muted" : ""}>
                    <td>{link.subject.label}</td>
                    <td>{link.object ? link.object.label : (RULES[link.rule] ?? link.rule)}</td>
                    <td>
                      {link.status === "rejected" ? "Rejected by a person" : METHODS[link.method]}
                      {link.method === "inferred" && link.status === "active" ? ` (${Math.round(link.confidence * 100)}% sure)` : ""}
                      {link.decided_by ? <div className="muted small">{link.decided_by}{link.note ? `: ${link.note}` : ""}</div> : null}
                    </td>
                    <td className="small">{describeLink(link)}</td>
                    <td>
                      {canEdit && link.type !== "violates" && link.decided_at === null && (
                        <>
                          <button type="button" className="link" aria-label={`Confirm ${link.subject.label} ${link.verb} ${link.object?.label}`} onClick={() => act(() => api.confirmRelationship(link.id), links.reload)}>
                            Confirm
                          </button>
                          <button type="button" className="link" aria-label={`Reject ${link.subject.label} ${link.verb} ${link.object?.label}`} onClick={() => act(() => api.rejectRelationship(link.id), links.reload)}>
                            Reject
                          </button>
                        </>
                      )}
                      {canEdit && link.decided_at !== null && (
                        <button type="button" className="link" onClick={() => act(() => api.reopenRelationship(link.id), links.reload)}>
                          Undo
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {links.data && links.data.count > links.data.results.length && (
            <p className="muted small">
              Showing the first {links.data.results.length} of {links.data.count}.
            </p>
          )}
        </section>
      )}

      <Standards canEdit={can("standards.manage")} />
    </section>
  );
}

function RolesForm(props: {
  registry: RelationsRegistry;
  rows: LayerRoleRow[];
  layers: Layer[];
  canEdit: boolean;
  onSave(roles: { role: string; layer: number | null; config?: Record<string, unknown> }[]): void;
}) {
  // Unset roles start on the suggested layer; nothing is saved until Save.
  const [chosen, setChosen] = useState<Record<string, number | null>>(() =>
    Object.fromEntries(props.rows.map((r) => [r.role, r.layer ?? r.suggested])),
  );
  const unsaved = props.rows.some((r) => (chosen[r.role] ?? null) !== r.layer);

  return (
    <section aria-label="Layers" className="card wide">
      <h2>Which layer holds what</h2>
      <table className="data">
        <thead>
          <tr>
            <th>Part</th>
            <th>Layer</th>
          </tr>
        </thead>
        <tbody>
          {props.registry.roles.map((role) => {
            const row = props.rows.find((r) => r.role === role.code);
            const options = props.layers.filter((l) => role.geometry.includes(l.geometry_type));
            const value = chosen[role.code] ?? null;
            return (
              <tr key={role.code}>
                <td>{role.label}</td>
                <td>
                  <select
                    aria-label={`Layer for ${role.label}`}
                    value={value ?? ""}
                    disabled={!props.canEdit}
                    onChange={(e) => setChosen({ ...chosen, [role.code]: e.target.value ? Number(e.target.value) : null })}
                  >
                    <option value="">Not in this project</option>
                    {options.map((l) => (
                      <option key={l.id} value={l.id}>
                        {l.name}
                      </option>
                    ))}
                  </select>
                  {row && row.layer === null && row.suggested !== null && value === row.suggested && <span className="muted small"> suggested</span>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {props.canEdit && (
        <div className="inline-form">
          <button
            type="button"
            disabled={!unsaved}
            onClick={() => props.onSave(props.rows.map((r) => ({ role: r.role, layer: chosen[r.role] ?? null, config: r.config })))}
          >
            Save
          </button>
          {unsaved && <span className="muted small">Not saved yet.</span>}
        </div>
      )}
    </section>
  );
}

const EMPTY: Partial<DevelopmentStandard> = { zone: "", min_setback_m: null, max_floors: null, max_coverage_pct: null, min_plot_m2: null, permit_required: false, build_in_flood_area: true };

function Standards({ canEdit }: { canEdit: boolean }) {
  const { api, districtId } = useSession();
  const list = useLoad(() => api.listStandards(), [api, districtId]);
  const [draft, setDraft] = useState<Partial<DevelopmentStandard> | null>(null);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => setDraft(null), [districtId]);

  const number = (value: string) => (value === "" ? null : Number(value));
  async function save() {
    if (!draft) return;
    setError(null);
    try {
      if (draft.id) await api.updateStandard(draft.id, draft);
      else await api.createStandard(draft);
      setDraft(null);
      list.reload();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <section aria-label="Development standards" className="card wide">
      <h2>Development standards</h2>
      <p className="muted small">
        What the district allows in each zone. A zone is matched to a parcel's land use (or the zoning layer). The standard with no
        zone is the district's default. With no standards at all, a 3 m setback is checked. They apply to every project in the
        district, at the next run.
      </p>
      <ErrorMessage error={error ?? list.error} />
      {list.data && list.data.length > 0 && (
        <table className="data">
          <thead>
            <tr>
              <th>Zone</th>
              <th>Setback (m)</th>
              <th>Floors</th>
              <th>Coverage (%)</th>
              <th>Plot (m²)</th>
              <th>Permit</th>
              <th>Flood-prone areas</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {list.data.map((s) => (
              <tr key={s.id}>
                <td>{s.zone || "Default"}</td>
                <td>{s.min_setback_m ?? "—"}</td>
                <td>{s.max_floors ?? "—"}</td>
                <td>{s.max_coverage_pct ?? "—"}</td>
                <td>{s.min_plot_m2 ?? "—"}</td>
                <td>{s.permit_required ? "required" : "—"}</td>
                <td>{s.build_in_flood_area ? "—" : "no building"}</td>
                <td>
                  {canEdit && (
                    <>
                      <button type="button" className="link" onClick={() => setDraft(s)}>
                        Edit
                      </button>
                      <button
                        type="button"
                        className="link"
                        aria-label={`Remove the ${s.zone || "default"} standard`}
                        onClick={async () => {
                          if (!window.confirm(`Remove the ${s.zone || "default"} standard?`)) return;
                          await api.deleteStandard(s.id).catch(setError);
                          list.reload();
                        }}
                      >
                        Remove
                      </button>
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {canEdit && !draft && (
        <button type="button" className="secondary" onClick={() => setDraft(EMPTY)}>
          Add a standard
        </button>
      )}
      {draft && (
        <form
          className="inline-form"
          aria-label="Standard"
          onSubmit={(e) => {
            e.preventDefault();
            void save();
          }}
        >
          <label>
            Zone (empty: the default)
            <input value={draft.zone ?? ""} onChange={(e) => setDraft({ ...draft, zone: e.target.value })} />
          </label>
          <label>
            Minimum setback (m)
            <input type="number" min={0} step="any" style={{ width: "6rem" }} value={draft.min_setback_m ?? ""} onChange={(e) => setDraft({ ...draft, min_setback_m: number(e.target.value) })} />
          </label>
          <label>
            Maximum floors
            <input type="number" min={0} style={{ width: "5rem" }} value={draft.max_floors ?? ""} onChange={(e) => setDraft({ ...draft, max_floors: number(e.target.value) })} />
          </label>
          <label>
            Maximum coverage (%)
            <input type="number" min={0} max={100} step="any" style={{ width: "6rem" }} value={draft.max_coverage_pct ?? ""} onChange={(e) => setDraft({ ...draft, max_coverage_pct: number(e.target.value) })} />
          </label>
          <label>
            Minimum plot (m²)
            <input type="number" min={0} step="any" style={{ width: "6rem" }} value={draft.min_plot_m2 ?? ""} onChange={(e) => setDraft({ ...draft, min_plot_m2: number(e.target.value) })} />
          </label>
          <label className="checkbox">
            <input type="checkbox" checked={draft.permit_required ?? false} onChange={(e) => setDraft({ ...draft, permit_required: e.target.checked })} /> Permit required
          </label>
          <label className="checkbox">
            <input type="checkbox" checked={!(draft.build_in_flood_area ?? true)} onChange={(e) => setDraft({ ...draft, build_in_flood_area: !e.target.checked })} /> No building in flood-prone areas
          </label>
          <button type="submit">Save standard</button>
          <button type="button" className="link" onClick={() => setDraft(null)}>
            Cancel
          </button>
        </form>
      )}
    </section>
  );
}
