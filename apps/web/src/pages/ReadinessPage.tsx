import type { ChecklistGroup, ChecklistKind, ChecklistRules, TemplateItem } from "@spatial/map-core";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { ErrorMessage } from "../components/ErrorMessage";
import { useLoad } from "../components/useLoad";
import { useSession } from "../session";
import { Progress } from "./ChecklistPage";

const GROUPS: Record<ChecklistGroup, string> = {
  authority: "1. Authority and set-up",
  planning_area: "2. Planning area",
  base_map: "3. Base map",
  existing: "4. Existing situation",
  people: "5. People and standards",
};

/** The district's readiness: every active project's score and blockers. */
export function ReadinessPage() {
  const { api, can, districtId } = useSession();
  const dashboard = useLoad(() => api.readinessDashboard(), [api, districtId]);

  return (
    <section className="page">
      <h1>Plan readiness</h1>
      <ErrorMessage error={dashboard.error} />
      {dashboard.data && (
        <>
          <p>
            District average <strong aria-label="District readiness">{dashboard.data.score}%</strong> across{" "}
            {dashboard.data.projects.length} project{dashboard.data.projects.length === 1 ? "" : "s"}.
          </p>
          <table className="data">
            <thead>
              <tr>
                <th>Project</th>
                <th>Score</th>
                <th>Progress</th>
                <th>Blockers</th>
              </tr>
            </thead>
            <tbody>
              {dashboard.data.projects.map((p) => (
                <tr key={p.project}>
                  <td>
                    <Link to={`/projects/${p.project}/checklist`}>{p.name}</Link>
                  </td>
                  <td>
                    {p.score}% <span className="muted small">({p.complete}/{p.total})</span>
                  </td>
                  <td style={{ minWidth: "10rem" }}>
                    <Progress value={p.score} label={`Readiness of ${p.name}`} />
                  </td>
                  <td className="small">
                    {p.blockers.length === 0
                      ? "—"
                      : p.blockers.slice(0, 3).map((b, i) => (
                          <div key={i}>
                            <strong>{b.title}</strong>: {b.problem}
                          </div>
                        ))}
                    {p.blockers.length > 3 && <div className="muted">and {p.blockers.length - 3} more</div>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {can("checklist.template") && <TemplateEditor />}
    </section>
  );
}

function rulesText(rules: ChecklistRules): string {
  const parts: string[] = [];
  if (rules.min_features !== undefined) parts.push(`≥ ${rules.min_features} features`);
  if (rules.min_coverage !== undefined) parts.push(`coverage ≥ ${rules.min_coverage}%`);
  if (rules.min_attributes !== undefined) parts.push(`attributes ≥ ${rules.min_attributes}%`);
  if (rules.max_age_days !== undefined) parts.push(`updated within ${rules.max_age_days} days`);
  if (rules.min_verified !== undefined) parts.push(`verified ≥ ${rules.min_verified}%`);
  if (rules.boundary_status) parts.push(`boundary ${rules.boundary_status}`);
  if (rules.no_overlaps) parts.push("no overlaps");
  return parts.join(", ");
}

/** The checklist used for the district's new projects. */
function TemplateEditor() {
  const { api, districtId } = useSession();
  const template = useLoad(() => api.getChecklistTemplate(), [api, districtId]);
  const [error, setError] = useState<unknown>(null);
  const [editing, setEditing] = useState<TemplateItem | null>(null);

  async function run(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      template.reload();
    } catch (err) {
      setError(err);
    }
  }

  const data = template.data;
  return (
    <section aria-label="Checklist template" className="stack">
      <h2>Checklist template</h2>
      <p className="muted small">
        New projects copy this checklist. Changes don't alter existing projects; they can pick up new items with "Add new
        template items".
        {data && (data.own ? " This district has its own template." : " This is the platform default.")}
      </p>
      <ErrorMessage error={error ?? template.error} />
      {data && (
        <>
          <div className="inline-form">
            {!data.own && (
              <button type="button" onClick={() => run(() => api.customiseChecklistTemplate())}>
                Customise for this district
              </button>
            )}
            {data.own && (
              <button
                type="button"
                className="link"
                onClick={() =>
                  window.confirm("Go back to the platform default? The district's own items are removed.") &&
                  run(() => api.revertChecklistTemplate())
                }
              >
                Revert to the platform default
              </button>
            )}
            <button
              type="button"
              className="secondary"
              onClick={() =>
                setEditing({ id: 0, group: "authority", key: "", title: "", description: "", kind: "document", domain: "", geometry_type: "", rules: {}, order: 999 })
              }
            >
              Add item
            </button>
          </div>
          <table className="data">
            <thead>
              <tr>
                <th>Group</th>
                <th>Item</th>
                <th>Kind</th>
                <th>Completion rules</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {data.items.map((item) => (
                <tr key={item.id}>
                  <td className="small">{GROUPS[item.group]}</td>
                  <td>{item.title}</td>
                  <td className="small">
                    {item.kind}
                    {item.domain ? ` · ${item.domain}` : ""}
                    {item.geometry_type ? ` · ${item.geometry_type}` : ""}
                  </td>
                  <td className="small">{rulesText(item.rules) || "—"}</td>
                  <td>
                    <button type="button" className="link" onClick={() => setEditing(item)}>
                      Edit
                    </button>
                    <button
                      type="button"
                      className="link"
                      aria-label={`Remove ${item.title}`}
                      onClick={() =>
                        window.confirm(`Remove "${item.title}" from the template?`) && run(() => api.deleteTemplateItem(item.id))
                      }
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {editing && (
        <div className="dialog">
          <TemplateItemForm
            item={editing}
            onClose={() => setEditing(null)}
            onSave={async (values) => {
              setError(null);
              try {
                if (editing.id) await api.updateTemplateItem(editing.id, values);
                else await api.createTemplateItem(values);
                setEditing(null);
                template.reload();
              } catch (err) {
                setError(err);
                throw err;
              }
            }}
          />
        </div>
      )}
    </section>
  );
}

const RULE_FIELDS: [keyof ChecklistRules, string][] = [
  ["min_features", "Minimum features"],
  ["min_coverage", "Minimum coverage %"],
  ["min_attributes", "Minimum attributes filled %"],
  ["max_age_days", "Newest data at most (days old)"],
  ["min_verified", "Minimum verified in the field %"],
];

function TemplateItemForm(props: {
  item: TemplateItem;
  onClose(): void;
  onSave(values: Omit<TemplateItem, "id">): Promise<void>;
}) {
  const [values, setValues] = useState(props.item);
  const [error, setError] = useState<unknown>(null);
  const set = (change: Partial<TemplateItem>) => setValues((v) => ({ ...v, ...change }));
  const setRule = (key: keyof ChecklistRules, raw: string) => {
    const rules = { ...values.rules } as Record<string, unknown>;
    if (raw === "") delete rules[key];
    else rules[key] = Number(raw);
    set({ rules: rules as ChecklistRules });
  };

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    const key = values.key || values.title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
    const { group, title, description, kind, domain, geometry_type, rules, order } = values;
    try {
      await props.onSave({ group, key, title, description, kind, domain, geometry_type, rules, order });
    } catch (err) {
      setError(err);
    }
  }

  return (
    <form className="card wide stack" role="dialog" aria-modal="true" aria-label="Checklist item" onSubmit={submit}>
      <h2>{props.item.id ? "Edit checklist item" : "New checklist item"}</h2>
      <label>
        Title
        <input value={values.title} onChange={(e) => set({ title: e.target.value })} required />
      </label>
      <label>
        Description
        <textarea rows={2} value={values.description} onChange={(e) => set({ description: e.target.value })} />
      </label>
      <div className="inline-form">
        <label>
          Group
          <select value={values.group} onChange={(e) => set({ group: e.target.value as ChecklistGroup })}>
            {Object.entries(GROUPS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Kind
          <select value={values.kind} onChange={(e) => {
              const kind = e.target.value as ChecklistKind;
              set({
                kind,
                domain: kind === "layer" ? values.domain || "A" : "",
                geometry_type: kind === "layer" ? values.geometry_type || "polygon" : "",
              });
            }} disabled={Boolean(props.item.id)}>
            <option value="document">Document or decision</option>
            <option value="layer">Map layer</option>
            <option value="boundary">Planning area boundary</option>
          </select>
        </label>
        {values.kind === "layer" && (
          <>
            <label>
              Domain
              <select value={values.domain} onChange={(e) => set({ domain: e.target.value })}>
                {"ABCDEFGHIJ".split("").map((d) => (
                  <option key={d} value={d}>
                    {d}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Geometry
              <select value={values.geometry_type} onChange={(e) => set({ geometry_type: e.target.value })}>
                <option value="">—</option>
                <option value="point">Point</option>
                <option value="line">Line</option>
                <option value="polygon">Polygon</option>
              </select>
            </label>
          </>
        )}
      </div>
      {values.kind === "layer" && (
        <fieldset>
          <legend>Completion rules (leave empty for none)</legend>
          <div className="inline-form">
            {RULE_FIELDS.map(([key, label]) => (
              <label key={key}>
                {label}
                <input
                  type="number"
                  min={0}
                  style={{ width: "6rem" }}
                  value={(values.rules[key] as number | undefined) ?? ""}
                  onChange={(e) => setRule(key, e.target.value)}
                />
              </label>
            ))}
          </div>
        </fieldset>
      )}
      <ErrorMessage error={error} />
      <div className="inline-form">
        <button type="submit">Save</button>
        <button type="button" className="link" onClick={props.onClose}>
          Cancel
        </button>
      </div>
    </form>
  );
}
