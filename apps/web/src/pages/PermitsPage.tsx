import type { GeoJSONGeometry, MapFeature, NewPermit, PermitFee, PermitKind, PermitRegistry, PermitSummary } from "@spatial/map-core";
import { useMemo, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ErrorMessage } from "../components/ErrorMessage";
import { useLoad } from "../components/useLoad";
import { useSession } from "../session";

const STATUS: Record<string, string> = {
  received: "Received",
  review: "With the Technical Sub-Committee",
  reported: "With the Spatial Planning Committee",
  granted: "Granted: permit fee due",
  deferred: "Deferred",
  refused: "Refused",
  issued: "Permit issued",
  withdrawn: "Withdrawn",
};
export const OUTCOME = { pass: "Meets it", fail: "Doesn't meet it", warn: "Look into it", unknown: "Can't tell from the map" };

/** "Due 12 Oct (r.44(6))", in red when the date has passed. */
export function Due({ permit }: { permit: PermitSummary }) {
  const due = permit.next_due;
  if (!due) return <span className="muted">—</span>;
  return (
    <span className={due.overdue ? "error" : undefined} title={due.rule}>
      {due.label}: {due.overdue ? "overdue since" : "by"} {due.due_on}
    </span>
  );
}

function checks(permit: PermitSummary): string {
  const c = permit.check_counts;
  if (!c) return "—";
  const parts = [c.fail ? `${c.fail} not met` : "", c.warn ? `${c.warn} to look into` : ""].filter(Boolean);
  return parts.length ? parts.join(", ") : "nothing against it";
}

/** "E, N" lines (in the project's coordinate system) to a closed polygon. */
export function ringFrom(text: string): GeoJSONGeometry | string {
  const points: number[][] = [];
  for (const line of text.split("\n").map((l) => l.trim()).filter(Boolean)) {
    const numbers = line.split(/[,;\s]+/).filter(Boolean).map(Number);
    if (numbers.length !== 2 || numbers.some((n) => !Number.isFinite(n))) return `"${line}" isn't an easting and a northing.`;
    points.push(numbers);
  }
  if (points.length < 3) return "Give at least three corners, one per line.";
  const [first, last] = [points[0]!, points[points.length - 1]!];
  if (first[0] !== last[0] || first[1] !== last[1]) points.push([...first]);
  return { type: "Polygon", coordinates: [points] };
}

function ReceiveForm(props: { projectId: number; registry: PermitRegistry; onReceived(id: number): void; onCancel(): void }) {
  const { api, districtId } = useSession();
  const [kind, setKind] = useState<PermitKind>("development");
  const categories = props.registry.categories.filter((c) => c.kind === kind);
  const [category, setCategory] = useState("building");
  const [values, setValues] = useState({ applicant_name: "", applicant_phone: "", applicant_email: "", applicant_address: "", proposed_use: "", description: "", received_on: "" });
  const [floors, setFloors] = useState("");
  const [siteBy, setSiteBy] = useState<"parcel" | "corners" | "later">("parcel");
  const [parcel, setParcel] = useState("");
  const [corners, setCorners] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  // The parcels layer, to pick a plot by its id.
  const parcels = useLoad(async () => {
    const roles = await api.getLayerRoles(props.projectId);
    const role = roles.roles.find((r) => r.role === "parcels" && r.layer !== null);
    if (!role || role.layer === null) return null;
    const field = String(role.config.id_field ?? "parcel_id");
    const page = await api.listFeatures(role.layer, { limit: 2000 });
    return { field, features: page.features };
  }, [api, props.projectId, districtId]);
  const label = (f: MapFeature) => String(f.properties[parcels.data?.field ?? ""] ?? `#${f.id}`);

  function set(key: keyof typeof values, value: string) {
    setValues((v) => ({ ...v, [key]: value }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    const data: NewPermit = { project: props.projectId, kind, category, applicant_name: values.applicant_name };
    for (const key of ["applicant_phone", "applicant_email", "applicant_address", "proposed_use", "description", "received_on"] as const) {
      if (values[key]) data[key] = values[key];
    }
    if (floors !== "") data.proposed_floors = Number(floors);
    if (siteBy === "parcel") {
      const found = parcels.data?.features.find((f) => label(f) === parcel.trim());
      if (!found) return setError(new Error(`No parcel "${parcel}" in the parcels layer.`));
      data.site_feature = found.id;
    } else if (siteBy === "corners") {
      const ring = ringFrom(corners);
      if (typeof ring === "string") return setError(new Error(ring));
      data.site_geometry = ring;
    }
    setBusy(true);
    try {
      props.onReceived((await api.createPermit(data)).id);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card wide stack" aria-label="Receive an application" onSubmit={submit}>
      <h2>Receive an application</h2>
      <ErrorMessage error={error} />
      <div className="inline-form">
        <label>
          Permit
          <select
            aria-label="Permit"
            value={kind}
            onChange={(e) => {
              const next = e.target.value as PermitKind;
              setKind(next);
              setCategory(props.registry.categories.find((c) => c.kind === next)!.code);
            }}
          >
            <option value="development">Development permit</option>
            <option value="planning">Planning permit</option>
          </select>
        </label>
        <label>
          For
          <select aria-label="For" value={category} onChange={(e) => setCategory(e.target.value)}>
            {categories.map((c) => (
              <option key={c.code} value={c.code}>
                {c.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Received on
          <input type="date" aria-label="Received on" value={values.received_on} onChange={(e) => set("received_on", e.target.value)} />
        </label>
      </div>
      <div className="inline-form">
        <label>
          Applicant
          <input required aria-label="Applicant" value={values.applicant_name} onChange={(e) => set("applicant_name", e.target.value)} />
        </label>
        <label>
          Phone
          <input value={values.applicant_phone} onChange={(e) => set("applicant_phone", e.target.value)} />
        </label>
        <label>
          Email
          <input type="email" value={values.applicant_email} onChange={(e) => set("applicant_email", e.target.value)} />
        </label>
        <label>
          Address
          <input value={values.applicant_address} onChange={(e) => set("applicant_address", e.target.value)} />
        </label>
      </div>
      <div className="inline-form">
        <label>
          Proposed use
          <input aria-label="Proposed use" value={values.proposed_use} onChange={(e) => set("proposed_use", e.target.value)} placeholder="e.g. Residential, two-storey house" />
        </label>
        <label>
          Storeys
          <input type="number" min={0} aria-label="Storeys" style={{ width: "5rem" }} value={floors} onChange={(e) => setFloors(e.target.value)} />
        </label>
        <label>
          Description
          <input value={values.description} onChange={(e) => set("description", e.target.value)} />
        </label>
      </div>
      <fieldset>
        <legend>The site</legend>
        <div className="inline-form">
          <label className="checkbox">
            <input type="radio" name="site" checked={siteBy === "parcel"} onChange={() => setSiteBy("parcel")} /> A parcel on the map
          </label>
          <label className="checkbox">
            <input type="radio" name="site" checked={siteBy === "corners"} onChange={() => setSiteBy("corners")} /> Its corner coordinates
          </label>
          <label className="checkbox">
            <input type="radio" name="site" checked={siteBy === "later"} onChange={() => setSiteBy("later")} /> Add it later
          </label>
        </div>
        {siteBy === "parcel" && (
          <label>
            Parcel id
            <input aria-label="Parcel id" list="permit-parcels" value={parcel} onChange={(e) => setParcel(e.target.value)} />
            <datalist id="permit-parcels">{parcels.data?.features.map((f) => <option key={f.id} value={label(f)} />)}</datalist>
            {parcels.data === null && !parcels.loading && (
              <span className="muted small"> No parcels layer is set for this project (Relationships, Layers): give the corners instead.</span>
            )}
          </label>
        )}
        {siteBy === "corners" && (
          <label>
            Corners, one per line: easting, northing (in the project's coordinate system)
            <textarea aria-label="Corner coordinates" rows={5} value={corners} onChange={(e) => setCorners(e.target.value)} placeholder={"1194820.5, 338250.1\n1194910.2, 338251.0\n…"} />
          </label>
        )}
      </fieldset>
      <p className="muted small">
        The application gets its number, and the Regulations' deadlines run from the day it was received: 7 days to acknowledge it, 14
        for the Technical Sub-Committee's checks and site visit, 21 for its report, 30 for the certificate.
      </p>
      <div className="inline-form">
        {/* The parcel is found in the list, so wait for the list. */}
        <button type="submit" disabled={busy || (siteBy === "parcel" && parcels.loading)}>
          {busy ? "Receiving…" : "Receive the application"}
        </button>
        <button type="button" className="link" onClick={props.onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function Fees({ registry, canEdit }: { registry: PermitRegistry; canEdit: boolean }) {
  const { api, districtId } = useSession();
  const list = useLoad(() => api.listPermitFees(), [api, districtId]);
  const [draft, setDraft] = useState<Omit<PermitFee, "id" | "updated_at"> | null>(null);
  const [error, setError] = useState<unknown>(null);
  const categoryLabel = (code: string) => registry.categories.find((c) => c.code === code)?.label ?? "every category";

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!draft) return;
    setError(null);
    try {
      await api.createPermitFee(draft);
      setDraft(null);
      list.reload();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <section aria-label="Fees" className="card wide">
      <h2>Fees</h2>
      <p className="muted small">
        From the Assembly's fee-fixing resolution: the processing fee paid with an application and the permit fee paid once it is
        granted. Staff see these when they record a receipt.
      </p>
      <ErrorMessage error={error ?? list.error} />
      {list.data?.length === 0 && <p>No fees entered yet.</p>}
      {list.data && list.data.length > 0 && (
        <table className="data">
          <thead>
            <tr>
              <th>Fee</th>
              <th>Stage</th>
              <th>Permit</th>
              <th>For</th>
              <th>Amount (GHS)</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {list.data.map((fee) => (
              <tr key={fee.id}>
                <td>{fee.label}</td>
                <td>{fee.stage === "processing" ? "Processing" : "Permit"}</td>
                <td>{fee.kind === "development" ? "Development" : "Planning"}</td>
                <td>{categoryLabel(fee.category)}</td>
                <td>{fee.amount}</td>
                <td>
                  {canEdit && (
                    <button
                      type="button"
                      className="link"
                      aria-label={`Remove ${fee.label}`}
                      onClick={async () => {
                        await api.deletePermitFee(fee.id).catch(setError);
                        list.reload();
                      }}
                    >
                      Remove
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {canEdit && !draft && (
        <button type="button" className="secondary" onClick={() => setDraft({ stage: "processing", kind: "development", category: "", label: "", amount: "" })}>
          Add a fee
        </button>
      )}
      {draft && (
        <form className="inline-form" aria-label="Fee" onSubmit={save}>
          <label>
            Stage
            <select aria-label="Stage" value={draft.stage} onChange={(e) => setDraft({ ...draft, stage: e.target.value as PermitFee["stage"] })}>
              <option value="processing">Processing</option>
              <option value="permit">Permit</option>
            </select>
          </label>
          <label>
            Permit
            <select aria-label="Fee for permit" value={draft.kind} onChange={(e) => setDraft({ ...draft, kind: e.target.value as PermitKind, category: "" })}>
              <option value="development">Development</option>
              <option value="planning">Planning</option>
            </select>
          </label>
          <label>
            For
            <select aria-label="Fee for category" value={draft.category} onChange={(e) => setDraft({ ...draft, category: e.target.value })}>
              <option value="">Every category</option>
              {registry.categories
                .filter((c) => c.kind === draft.kind)
                .map((c) => (
                  <option key={c.code} value={c.code}>
                    {c.label}
                  </option>
                ))}
            </select>
          </label>
          <label>
            Name
            <input required aria-label="Fee name" value={draft.label} onChange={(e) => setDraft({ ...draft, label: e.target.value })} />
          </label>
          <label>
            Amount (GHS)
            <input required type="number" min={0} step="0.01" aria-label="Amount" style={{ width: "7rem" }} value={draft.amount} onChange={(e) => setDraft({ ...draft, amount: e.target.value })} />
          </label>
          <button type="submit">Save fee</button>
          <button type="button" className="link" onClick={() => setDraft(null)}>
            Cancel
          </button>
        </form>
      )}
    </section>
  );
}

/** A project's permit applications: what is open, what is due, and receiving a new one. */
export function PermitsPage() {
  const { projectId } = useParams();
  const id = Number(projectId);
  const navigate = useNavigate();
  const { api, can, districtId } = useSession();
  const [status, setStatus] = useState("");
  const [overdue, setOverdue] = useState(false);
  const [q, setQ] = useState("");
  const [receiving, setReceiving] = useState(false);
  const registry = useLoad(() => api.permitRegistry(), [api]);
  const list = useLoad(() => api.listPermits({ project: id, status: status || undefined, q: q || undefined, overdue }), [api, id, districtId, status, overdue, q]);
  const summary = list.data?.summary;
  const statuses = useMemo(() => Object.entries(summary?.by_status ?? {}), [summary]);

  return (
    <section className="page">
      <p>
        <Link to={`/projects/${id}`}>← Back to the project</Link>
      </p>
      <h1>Permits</h1>
      <p className="muted">
        Planning and development permit applications, from the day they are received to the certificate, with the deadlines the
        Regulations set (L.I. 2384 r.44–45).
      </p>
      <ErrorMessage error={list.error ?? registry.error} />
      {summary && (
        <dl className="facts" aria-label="Summary">
          <dt>Open</dt>
          <dd>{summary.open}</dd>
          <dt>With a deadline passed</dt>
          <dd className={summary.overdue ? "error" : undefined}>{summary.overdue}</dd>
          <dt>Shown</dt>
          <dd>{summary.total}</dd>
        </dl>
      )}
      <div className="inline-form">
        <label>
          Status
          <select aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All</option>
            {statuses.map(([code, count]) => (
              <option key={code} value={code}>
                {STATUS[code] ?? code} ({count})
              </option>
            ))}
          </select>
        </label>
        <label className="checkbox">
          <input type="checkbox" checked={overdue} onChange={(e) => setOverdue(e.target.checked)} /> Only those with a deadline passed
        </label>
        <label>
          Find
          <input aria-label="Find" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Number or applicant" />
        </label>
        {can("permit.process") && !receiving && registry.data && (
          <button type="button" onClick={() => setReceiving(true)}>
            Receive an application
          </button>
        )}
      </div>
      {receiving && registry.data && (
        <ReceiveForm projectId={id} registry={registry.data} onCancel={() => setReceiving(false)} onReceived={(permit) => navigate(`/projects/${id}/permits/${permit}`)} />
      )}
      {list.data?.results.length === 0 && <p>No applications {status || overdue || q ? "match" : "yet"}.</p>}
      {list.data && list.data.results.length > 0 && (
        <table className="data">
          <thead>
            <tr>
              <th>Number</th>
              <th>Applicant</th>
              <th>For</th>
              <th>Received</th>
              <th>Status</th>
              <th>Next step</th>
              <th>Checks</th>
            </tr>
          </thead>
          <tbody>
            {list.data.results.map((permit) => (
              <tr key={permit.id}>
                <td>
                  <Link to={`/projects/${id}/permits/${permit.id}`}>{permit.number}</Link>
                </td>
                <td>{permit.applicant_name}</td>
                <td>{permit.category_label}</td>
                <td>{permit.received_on}</td>
                <td>{permit.status_label}</td>
                <td>
                  <Due permit={permit} />
                </td>
                <td className="small">{checks(permit)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {registry.data && <Fees registry={registry.data} canEdit={can("permit.settings")} />}
    </section>
  );
}
