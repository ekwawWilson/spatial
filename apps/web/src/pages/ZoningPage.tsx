import type { NationalZone, SchemeDeadline, ZoningScheme } from "@spatial/map-core";
import { useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { ErrorMessage } from "../components/ErrorMessage";
import { useLoad } from "../components/useLoad";
import { useSession } from "../session";

const STATUS = { draft: "Draft", approved: "Approved", adopted: "Existing scheme adopted" };
const DEADLINES: [keyof ZoningScheme["deadlines"], string][] = [
  ["prepare", "Prepare the scheme"],
  ["send_to_luspa", "Send a copy to LUSPA"],
  ["update", "Next update"],
];

function Deadline({ label, deadline }: { label: string; deadline: SchemeDeadline }) {
  const state = deadline.done_on ? `done on ${deadline.done_on}` : deadline.overdue ? `overdue since ${deadline.due_on}` : `due ${deadline.due_on}`;
  return (
    <li className={deadline.overdue ? "error" : undefined} title={deadline.rule}>
      {label}: {state} <span className="muted small">({deadline.rule})</span>
    </li>
  );
}

type Draft = Partial<ZoningScheme>;
const NEW: Draft = { name: "", status: "draft", structure_plan_approved_on: null, approved_on: null, effective_on: null, sent_to_luspa_on: null, update_every_months: 60, notes: "" };

function SchemeForm(props: { draft: Draft; onChange(draft: Draft): void; onSave(): void; onCancel(): void }) {
  const { draft } = props;
  const day = (key: "structure_plan_approved_on" | "approved_on" | "effective_on" | "sent_to_luspa_on", label: string) => (
    <label>
      {label}
      <input type="date" aria-label={label} value={draft[key] ?? ""} onChange={(e) => props.onChange({ ...draft, [key]: e.target.value || null })} />
    </label>
  );
  return (
    <form
      className="stack"
      aria-label="Zoning scheme"
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        props.onSave();
      }}
    >
      <div className="inline-form">
        <label>
          Name
          <input required value={draft.name ?? ""} onChange={(e) => props.onChange({ ...draft, name: e.target.value })} placeholder="e.g. Kasoa zoning scheme" />
        </label>
        <label>
          Status
          <select aria-label="Status" value={draft.status ?? "draft"} onChange={(e) => props.onChange({ ...draft, status: e.target.value as ZoningScheme["status"] })}>
            <option value="draft">Draft</option>
            <option value="approved">Approved</option>
            <option value="adopted">Existing scheme adopted</option>
          </select>
        </label>
        <label>
          Update every (months)
          <input
            type="number"
            min={1}
            max={240}
            style={{ width: "6rem" }}
            value={draft.update_every_months ?? 60}
            onChange={(e) => props.onChange({ ...draft, update_every_months: Number(e.target.value) })}
          />
        </label>
      </div>
      <div className="inline-form">
        {day("structure_plan_approved_on", "Structure plan approved on")}
        {day("approved_on", "Scheme approved on")}
        {day("effective_on", "In effect from")}
        {day("sent_to_luspa_on", "Sent to LUSPA on")}
      </div>
      <label>
        Notes
        <input value={draft.notes ?? ""} onChange={(e) => props.onChange({ ...draft, notes: e.target.value })} />
      </label>
      <div className="inline-form">
        <button type="submit">Save scheme</button>
        <button type="button" className="link" onClick={props.onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function Register({ projectId, canEdit }: { projectId: number; canEdit: boolean }) {
  const { api, districtId } = useSession();
  const list = useLoad(() => api.listZoningSchemes(projectId), [api, projectId, districtId]);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [error, setError] = useState<unknown>(null);

  async function save() {
    if (!draft) return;
    setError(null);
    try {
      if (draft.id) await api.updateZoningScheme(draft.id, draft);
      else await api.createZoningScheme({ ...draft, project: projectId, name: draft.name ?? "" });
      setDraft(null);
      list.reload();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <section aria-label="Zoning scheme register" className="card wide">
      <h2>Zoning scheme register</h2>
      <p className="muted small">
        The Regulations (L.I. 2384 r.29) ask for a zoning scheme within 90 days of the structure plan's approval, a copy to LUSPA within
        28 days of the scheme's approval, and a schedule for updating it. Record the dates here and the register shows what is due.
      </p>
      <ErrorMessage error={error ?? list.error} />
      {list.data?.length === 0 && <p>No zoning scheme recorded for this project yet.</p>}
      {list.data?.map((scheme) => (
        <article key={scheme.id} className="stack" aria-label={scheme.name}>
          <h3>
            {scheme.name} <span className="muted small">· {STATUS[scheme.status]}</span>
          </h3>
          <dl className="facts">
            <dt>Approved</dt>
            <dd>{scheme.approved_on ?? "—"}</dd>
            <dt>In effect from</dt>
            <dd>{scheme.effective_on ?? "—"}</dd>
            <dt>Sent to LUSPA</dt>
            <dd>{scheme.sent_to_luspa_on ?? "—"}</dd>
          </dl>
          <ul>
            {DEADLINES.map(([key, label]) => {
              const deadline = scheme.deadlines[key];
              return deadline ? <Deadline key={key} label={label} deadline={deadline} /> : null;
            })}
          </ul>
          {scheme.notes && <p className="muted small">{scheme.notes}</p>}
          {canEdit && (
            <div className="inline-form">
              <button type="button" className="link" onClick={() => setDraft(scheme)}>
                Edit
              </button>
              <button
                type="button"
                className="link"
                aria-label={`Remove ${scheme.name}`}
                onClick={async () => {
                  if (!window.confirm(`Remove "${scheme.name}" from the register?`)) return;
                  await api.deleteZoningScheme(scheme.id).catch(setError);
                  list.reload();
                }}
              >
                Remove
              </button>
            </div>
          )}
        </article>
      ))}
      {canEdit && !draft && (
        <button type="button" className="secondary" onClick={() => setDraft(NEW)}>
          Record a zoning scheme
        </button>
      )}
      {draft && <SchemeForm draft={draft} onChange={setDraft} onSave={() => void save()} onCancel={() => setDraft(null)} />}
    </section>
  );
}

function standardText(zone: NationalZone): string {
  const s = zone.standard;
  if (!s) return "—";
  const width = s.min_width_m === null ? "" : `, at least ${s.min_width_m} m wide`;
  return `Plot at least ${s.min_plot_m2?.toLocaleString("en-GB")} m²${width}; coverage up to ${s.max_coverage_pct}%; ${zone.height}; setbacks ${s.front_setback_m} m front, ${s.side_setback_m} m side, ${s.rear_setback_m} m back`;
}

function Zones() {
  const { api } = useSession();
  const zones = useLoad(() => api.nationalZones(), [api]);
  const groups = [...new Set(zones.data?.zones.map((z) => z.group) ?? [])];
  return (
    <section aria-label="National zones" className="card wide">
      <h2>National zones and standards</h2>
      <p className="muted small">
        From {zones.data?.source ?? "LUSPA's zoning standards"}. Use these codes in the zoning layer's zone field: the checks and the
        colours recognise them however they are written ("Re A", "ReA", "Residential Zone A"). District administrators adopt the site
        standards for the district under Relationships, Development standards.
      </p>
      <ErrorMessage error={zones.error} />
      {groups.map((group) => (
        <div key={group}>
          <h3>{group}</h3>
          <table className="data">
            <thead>
              <tr>
                <th>Colour</th>
                <th>Code</th>
                <th>Zone</th>
                <th>Site standards</th>
              </tr>
            </thead>
            <tbody>
              {zones.data?.zones
                .filter((z) => z.group === group)
                .map((zone) => (
                  <tr key={zone.code}>
                    <td>
                      <span
                        role="img"
                        aria-label={`${zone.code} colour ${zone.colour}`}
                        title={zone.pattern || zone.colour}
                        style={{ display: "inline-block", width: "2rem", height: "1.1rem", background: zone.colour, border: "1px solid #555" }}
                      />
                      {zone.pattern && <div className="muted small">{zone.pattern}</div>}
                    </td>
                    <td>
                      <strong>{zone.code}</strong>
                    </td>
                    <td>
                      {zone.name}
                      {(zone.permitted.length > 0 || zone.prohibited.length > 0) && (
                        <details>
                          <summary>Permissible and prohibited uses</summary>
                          <p className="small">
                            <strong>Permissible:</strong> {zone.permitted.join("; ")}.
                          </p>
                          <p className="small">
                            <strong>Prohibited:</strong> {zone.prohibited.join("; ")}.
                          </p>
                        </details>
                      )}
                    </td>
                    <td className="small">{standardText(zone)}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      ))}
    </section>
  );
}

/** A project's zoning: its scheme register, the national zones, and the standard colours. */
export function ZoningPage() {
  const { projectId } = useParams();
  const id = Number(projectId);
  const { api, can } = useSession();
  const canEdit = can("relations.edit");
  const [error, setError] = useState<unknown>(null);
  const [note, setNote] = useState<string | null>(null);

  async function colour() {
    setError(null);
    setNote(null);
    try {
      const result = await api.colourZoningLayer(id);
      const unknown = result.unknown.length ? ` Not recognised, left grey: ${result.unknown.join(", ")}.` : "";
      setNote(
        result.coloured.length
          ? `The zoning layer is now coloured by zone: ${result.coloured.join(", ")}.${unknown}`
          : `No zone in the zoning layer matches a national code.${unknown}`,
      );
    } catch (err) {
      setError(err);
    }
  }

  return (
    <section className="page">
      <p>
        <Link to={`/projects/${id}`}>← Back to the project</Link>
      </p>
      <h1>Zoning</h1>
      <ErrorMessage error={error} />
      {note && <p role="status">{note}</p>}
      <Register projectId={id} canEdit={canEdit} />
      {canEdit && (
        <section aria-label="Zone colours" className="card wide">
          <h2>Zone colours</h2>
          <p className="muted small">
            Colours the project's zoning layer by zone in the national colour codes, so plans read the same in every district. Zones
            drawn with a pattern in the standards get their background colour.
          </p>
          <button type="button" className="secondary" onClick={() => void colour()}>
            Colour the zoning layer in the national colours
          </button>
        </section>
      )}
      <Zones />
    </section>
  );
}
