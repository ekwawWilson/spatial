import type { LandApplication, LandClock, LandKind, LandRegistry, LandSummary, MapFeature, NewLandApplication } from "@spatial/map-core";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ErrorMessage } from "../components/ErrorMessage";
import { useLoad } from "../components/useLoad";
import { saveBlob } from "../components/workspace/ExportDialog";
import { useSession } from "../session";

function Next({ step }: { step: LandClock | null }) {
  if (!step) return <span className="muted">—</span>;
  return (
    <span className={step.overdue ? "error" : undefined}>
      {step.label}
      {step.due_on && (step.overdue ? `: overdue since ${step.due_on}` : `: by ${step.due_on}`)}
    </span>
  );
}

function ReceiveForm(props: { projectId: number; registry: LandRegistry; onReceived(id: number): void; onCancel(): void }) {
  const { api, districtId } = useSession();
  const [kind, setKind] = useState<LandKind>("rezoning");
  const [values, setValues] = useState({ applicant_name: "", applicant_phone: "", applicant_address: "", description: "", parcels: "", proposed_zone: "", current_use: "", proposed_use: "", lots: "", received_on: "" });
  const [ground, setGround] = useState("structure_plan");
  const [circumstance, setCircumstance] = useState(props.registry.circumstances[0]?.code ?? "other");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const set = (key: keyof typeof values, value: string) => setValues((v) => ({ ...v, [key]: value }));
  const spec = props.registry.kinds.find((k) => k.code === kind)!;

  // The parcels layer, to find each parcel by its id.
  const parcels = useLoad(async () => {
    const roles = await api.getLayerRoles(props.projectId);
    const role = roles.roles.find((r) => r.role === "parcels" && r.layer !== null);
    if (!role || role.layer === null) return null;
    const field = String(role.config.id_field ?? "parcel_id");
    const page = await api.listFeatures(role.layer, { limit: 2000 });
    return { field, features: page.features };
  }, [api, props.projectId, districtId]);
  const label = (f: MapFeature) => String(f.properties[parcels.data?.field ?? ""] ?? `#${f.id}`);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    const wanted = values.parcels.split(/[,;\n]+/).map((p) => p.trim()).filter(Boolean);
    const ids: number[] = [];
    for (const name of wanted) {
      const found = parcels.data?.features.find((f) => label(f) === name);
      if (!found) return setError(new Error(`No parcel "${name}" in the parcels layer.`));
      ids.push(found.id);
    }
    if (ids.length === 0) return setError(new Error("Give the parcel the application is about."));
    const data: NewLandApplication = { project: props.projectId, kind, applicant_name: values.applicant_name, parcels: ids };
    for (const key of ["applicant_phone", "applicant_address", "description", "received_on"] as const) {
      if (values[key]) data[key] = values[key];
    }
    if (kind === "rezoning") {
      data.proposed_zone = values.proposed_zone;
      data.ground = ground;
      if (ground === "special") data.circumstance = circumstance;
    }
    if (kind === "change_of_use") {
      data.current_use = values.current_use;
      data.proposed_use = values.proposed_use;
    }
    if (kind === "subdivision" && values.lots) data.lots = Number(values.lots);
    setBusy(true);
    try {
      props.onReceived((await api.receiveLandApplication(data)).id);
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
          For
          <select aria-label="For" value={kind} onChange={(e) => setKind(e.target.value as LandKind)}>
            {props.registry.kinds.map((k) => (
              <option key={k.code} value={k.code}>
                {k.label}
                {k.form && ` (Form ${k.form})`}
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
          <input aria-label="Phone" value={values.applicant_phone} onChange={(e) => set("applicant_phone", e.target.value)} />
        </label>
        <label>
          Address
          <input aria-label="Address" value={values.applicant_address} onChange={(e) => set("applicant_address", e.target.value)} />
        </label>
      </div>
      <label>
        {kind === "consolidation" ? "Parcel ids to be joined, separated by commas" : "Parcel id (several: separate with commas)"}
        <input required aria-label="Parcel ids" value={values.parcels} onChange={(e) => set("parcels", e.target.value)} placeholder="e.g. P-014" />
        {parcels.data === null && !parcels.loading && (
          <span className="muted small"> No parcels layer is set for this project (Relationships, Layers).</span>
        )}
      </label>
      {kind === "rezoning" && (
        <>
          <div className="inline-form">
            <label>
              Zone asked for
              <input required aria-label="Zone asked for" value={values.proposed_zone} onChange={(e) => set("proposed_zone", e.target.value)} placeholder="e.g. Co A" />
            </label>
            <label>
              Why (r.33(2))
              <select aria-label="Why" value={ground} onChange={(e) => setGround(e.target.value)}>
                {props.registry.grounds.map((g) => (
                  <option key={g.code} value={g.code}>
                    {g.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {ground === "special" && (
            <label>
              The special circumstance (r.33(3))
              <select aria-label="Special circumstance" value={circumstance} onChange={(e) => setCircumstance(e.target.value)}>
                {props.registry.circumstances.map((c) => (
                  <option key={c.code} value={c.code}>
                    {c.label}
                  </option>
                ))}
              </select>
            </label>
          )}
        </>
      )}
      {kind === "change_of_use" && (
        <div className="inline-form">
          <label>
            Present use
            <input aria-label="Present use" value={values.current_use} onChange={(e) => set("current_use", e.target.value)} />
          </label>
          <label>
            Use asked for
            <input required aria-label="Use asked for" value={values.proposed_use} onChange={(e) => set("proposed_use", e.target.value)} />
          </label>
        </div>
      )}
      {kind === "subdivision" && (
        <label>
          Into how many plots
          <input type="number" min={2} aria-label="Plots" style={{ width: "6rem" }} value={values.lots} onChange={(e) => set("lots", e.target.value)} />
        </label>
      )}
      <label>
        The proposal
        <textarea aria-label="The proposal" rows={2} value={values.description} onChange={(e) => set("description", e.target.value)} />
      </label>
      <p className="muted small">
        {spec.label} ({spec.rule}): the application gets its number and the Regulations' days run from the day it was received. A
        decision is due within {spec.decide_days} days ({spec.decide_rule}).
      </p>
      <div className="inline-form">
        {/* The parcels are found in the list, so wait for the list. */}
        <button type="submit" disabled={busy || parcels.loading}>
          {busy ? "Receiving…" : "Receive the application"}
        </button>
        <button type="button" className="link" onClick={props.onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

/** A project's applications for re-zoning, change of use, subdivision and consolidation. */
export function LandApplicationsPage() {
  const { projectId } = useParams();
  const id = Number(projectId);
  const navigate = useNavigate();
  const { api, can, districtId } = useSession();
  const registry = useLoad(() => api.landRegistry(), [api]);
  const [kind, setKind] = useState("");
  const [receiving, setReceiving] = useState(false);
  const list = useLoad(() => api.listLandApplications({ project: id, kind: kind || undefined }), [api, id, districtId, kind]);
  const summary = list.data?.summary;

  return (
    <section className="page">
      <p>
        <Link to={`/projects/${id}`}>← Back to the project</Link>
      </p>
      <h1>Re-zoning, change of use and subdivision</h1>
      <p className="muted">
        Applications that change the land itself, with every step and time limit the Regulations set: re-zoning (L.I. 2384 r.33), change
        of use (r.34), and the subdivision or consolidation of land (r.54).
      </p>
      <ErrorMessage error={list.error ?? registry.error} />
      {summary && (
        <dl className="facts" aria-label="Summary">
          <dt>Open</dt>
          <dd>{summary.open}</dd>
          <dt>With a step overdue</dt>
          <dd className={summary.overdue ? "error" : undefined}>{summary.overdue}</dd>
        </dl>
      )}
      <div className="inline-form">
        <label>
          Show
          <select aria-label="Show" value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="">All applications</option>
            {registry.data?.kinds.map((k) => (
              <option key={k.code} value={k.code}>
                {k.label}
              </option>
            ))}
          </select>
        </label>
        {can("permit.process") && !receiving && registry.data && (
          <button type="button" onClick={() => setReceiving(true)}>
            Receive an application
          </button>
        )}
      </div>
      {receiving && registry.data && (
        <ReceiveForm projectId={id} registry={registry.data} onCancel={() => setReceiving(false)} onReceived={(made) => navigate(`/projects/${id}/land/${made}`)} />
      )}
      {list.data?.results.length === 0 && <p>No applications {kind ? "of this kind" : "yet"}.</p>}
      {list.data && list.data.results.length > 0 && (
        <table className="data" aria-label="Applications">
          <thead>
            <tr>
              <th>Application</th>
              <th>Applicant</th>
              <th>Received</th>
              <th>Status</th>
              <th>Next</th>
            </tr>
          </thead>
          <tbody>
            {list.data.results.map((item: LandSummary) => (
              <tr key={item.id}>
                <td>
                  <Link to={`/projects/${id}/land/${item.id}`}>{item.number}</Link>
                  <div className="muted small">{item.kind_label}</div>
                </td>
                <td>{item.applicant_name}</td>
                <td>{item.received_on}</td>
                <td>{item.status_label}</td>
                <td>
                  <Next step={item.next_step} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function when(clock: LandClock): string {
  if (clock.done_on) return `Done ${clock.done_on}${clock.late ? `, late (due ${clock.due_on})` : ""}`;
  if (clock.due_on) return clock.overdue ? `Overdue since ${clock.due_on}` : `Due by ${clock.due_on}`;
  return clock.days === null ? "No time set" : "Not started to run";
}

/** One application: its steps and their dates, the comments on it, and the decision. */
export function LandApplicationPage() {
  const { projectId, applicationId } = useParams();
  const { api, can, districtId } = useSession();
  const loaded = useLoad(() => api.getLandApplication(Number(applicationId)), [api, applicationId, districtId]);
  const registry = useLoad(() => api.landRegistry(), [api]);
  const [item, setItem] = useState<LandApplication | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [note, setNote] = useState<string | null>(null);
  const [stepNote, setStepNote] = useState<Record<string, string>>({});
  const [comment, setComment] = useState({ kind: "objection", name: "", contact: "", text: "" });
  const [reply, setReply] = useState<Record<number, string>>({});
  const [answers, setAnswers] = useState<Record<string, { met: boolean; note: string }>>({});
  const [approve, setApprove] = useState(true);
  const [terms, setTerms] = useState("");
  const [deferReason, setDeferReason] = useState("");
  useEffect(() => {
    setItem(loaded.data);
    if (loaded.data) setAnswers(loaded.data.assessment);
  }, [loaded.data]);

  const act = async (action: () => Promise<LandApplication>, done: string) => {
    setError(null);
    setNote(null);
    try {
      setItem(await action());
      setNote(done);
    } catch (err) {
      setError(err);
    }
  };
  const canProcess = can("permit.process");
  const canDecide = can("permit.decide");
  const open = item !== null && (item.status === "received" || item.status === "deferred");
  const live = item !== null && item.status !== "withdrawn" && item.status !== "refused";

  return (
    <section className="page">
      <p>
        <Link to={`/projects/${projectId}/land`}>← All applications</Link>
      </p>
      <ErrorMessage error={error ?? loaded.error ?? registry.error} />
      {note && <p role="status">{note}</p>}
      {item && registry.data && (
        <>
          <h1>
            {item.number} <span className="muted small">· {item.status_label}</span>
          </h1>
          <dl className="facts" aria-label="Application">
            <dt>For</dt>
            <dd>
              {item.kind_label} <span className="muted small">({item.form ? `Form ${item.form}, ` : ""}{item.rule})</span>
            </dd>
            <dt>Asks for</dt>
            <dd>{item.summary}</dd>
            <dt>Applicant</dt>
            <dd>
              {item.applicant_name}
              {item.applicant_phone !== "restricted" && item.applicant_phone && <span className="muted small"> {item.applicant_phone}</span>}
            </dd>
            <dt>Land</dt>
            <dd>
              {item.parcels.map((p) => `${p.label} (${p.area_m2.toLocaleString()} m²)`).join(", ") || "—"}
              {item.zone.value && (
                <span className="muted small">
                  {" "}
                  zoned {item.zone.national ? `${item.zone.national}, ${item.zone.name}` : item.zone.value}
                </span>
              )}
            </dd>
            <dt>Received</dt>
            <dd>{item.received_on}</dd>
            {item.comments_close_on && (
              <>
                <dt>Public comments</dt>
                <dd>
                  until {item.comments_close_on} <span className="muted small">({item.comment_rule})</span>
                </dd>
              </>
            )}
            {item.deferred_on && (
              <>
                <dt>Deferred</dt>
                <dd>
                  {item.deferred_on}: {item.defer_reason}
                </dd>
              </>
            )}
            {item.decided_on && (
              <>
                <dt>Decided</dt>
                <dd>
                  {item.decided_on}
                  {item.conditions && <div className="small">Conditions: {item.conditions}</div>}
                  {item.reasons && <div className="small">Reasons: {item.reasons}</div>}
                </dd>
              </>
            )}
          </dl>
          {item.description && <p>{item.description}</p>}

          <section aria-label="Steps and deadlines" className="card wide">
            <h2>Steps and deadlines</h2>
            <table className="data">
              <thead>
                <tr>
                  <th>Step</th>
                  <th>Rule</th>
                  <th>When</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {item.clocks.map((clock) => (
                  <tr key={clock.code}>
                    <td>
                      {clock.label}
                      {clock.note && <div className="muted small">{clock.note}</div>}
                    </td>
                    <td className="small">
                      {clock.rule}
                      {clock.days !== null && `: ${clock.days} days`}
                    </td>
                    <td className={clock.overdue || clock.late ? "error" : undefined}>{when(clock)}</td>
                    <td>
                      {canProcess && live && clock.code !== "decide" && !clock.done_on && (
                        <span className="inline-form">
                          <input
                            aria-label={`Note for: ${clock.label}`}
                            placeholder="Note (e.g. the newspaper)"
                            value={stepNote[clock.code] ?? ""}
                            onChange={(e) => setStepNote({ ...stepNote, [clock.code]: e.target.value })}
                          />
                          <button
                            type="button"
                            className="secondary"
                            aria-label={`Done today: ${clock.label}`}
                            onClick={() => void act(() => api.landStep(item.id, { step: clock.code, note: stepNote[clock.code] ?? "" }), "Step recorded.")}
                          >
                            Done today
                          </button>
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {item.papers.length > 0 && (
              <div className="inline-form">
                {item.papers.map((paper) => (
                  <button key={paper.code} type="button" className="secondary" onClick={async () => saveBlob(await api.landPaper(item.id, paper.code), `${paper.code}-${item.number.replace(/\//g, "-")}.pdf`)}>
                    Download: {paper.label}
                  </button>
                ))}
              </div>
            )}
          </section>

          {item.kind === "rezoning" && (
            <section aria-label="Abutting land" className="card wide">
              <h2>Owners of abutting land</h2>
              <p className="muted small">
                The parcels that touch the land, from the map. The applicant gives each owner notice on Form 35 (r.33(8)–(10)); where an
                owner is unknown, by two newspaper publications or a notice posted near the land.
              </p>
              {item.abutting.length === 0 ? (
                <p>No parcel on the map touches this land.</p>
              ) : (
                <ul>
                  {item.abutting.map((a) => (
                    <li key={a.id}>
                      <strong>{a.label}</strong>: {a.owner === "restricted" ? "owner on record (restricted)" : a.owner || <span className="error">owner not on record</span>}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}

          {item.kind === "change_of_use" && (
            <form
              className="card wide stack"
              aria-label="Tests of r.34"
              onSubmit={(e: FormEvent) => {
                e.preventDefault();
                void act(() => api.landAssess(item.id, answers), "Assessment saved.");
              }}
            >
              <h2>The tests of r.34</h2>
              <p className="muted small">
                A change of use may be allowed only where every one is met.
                {item.zone.prohibited_uses.length > 0 && ` Uses the district prohibits in this zone: ${item.zone.prohibited_uses.join(", ")}.`}
              </p>
              {registry.data.use_tests.map((test) => (
                <div key={test.code} className="inline-form">
                  <label>
                    {test.label} <span className="muted small">({test.rule})</span>
                    <select
                      aria-label={test.label}
                      disabled={!canProcess || !open}
                      value={answers[test.code] === undefined ? "" : answers[test.code]!.met ? "met" : "not"}
                      onChange={(e) => {
                        const next = { ...answers };
                        if (e.target.value === "") delete next[test.code];
                        else next[test.code] = { met: e.target.value === "met", note: answers[test.code]?.note ?? "" };
                        setAnswers(next);
                      }}
                    >
                      <option value="">Not assessed</option>
                      <option value="met">Met</option>
                      <option value="not">Not met</option>
                    </select>
                  </label>
                  {answers[test.code] !== undefined && (
                    <input
                      aria-label={`Note: ${test.label}`}
                      placeholder="Why"
                      disabled={!canProcess || !open}
                      value={answers[test.code]!.note}
                      onChange={(e) => setAnswers({ ...answers, [test.code]: { met: answers[test.code]!.met, note: e.target.value } })}
                    />
                  )}
                </div>
              ))}
              {canProcess && open && (
                <div className="inline-form">
                  <button type="submit">Save the assessment</button>
                </div>
              )}
            </form>
          )}

          <section aria-label="Comments and objections" className="card wide">
            <h2>Comments and objections</h2>
            {item.comments.length === 0 && <p className="muted">None received.</p>}
            {item.comments.map((c) => (
              <article key={c.id} className="stack">
                <p>
                  <strong>{c.kind_label}</strong>, {c.received_on}
                  {c.name !== "restricted" && `, ${c.name}`}: {c.text}
                </p>
                {c.response ? (
                  <p className="small">
                    The applicant's reply ({c.responded_on}): {c.response}
                  </p>
                ) : (
                  canProcess &&
                  live && (
                    <span className="inline-form">
                      <input aria-label={`Applicant's reply to comment ${c.id}`} placeholder="The applicant's reply" value={reply[c.id] ?? ""} onChange={(e) => setReply({ ...reply, [c.id]: e.target.value })} />
                      <button type="button" className="secondary" disabled={!reply[c.id]} onClick={() => void act(() => api.landRespond(item.id, { comment: c.id, response: reply[c.id] ?? "" }), "Reply recorded.")}>
                        Record the reply
                      </button>
                    </span>
                  )
                )}
              </article>
            ))}
            {canProcess && open && (
              <form
                className="stack"
                aria-label="Record a comment"
                onSubmit={(e: FormEvent) => {
                  e.preventDefault();
                  void act(() => api.landComment(item.id, comment), "Comment recorded.").then(() => setComment({ ...comment, name: "", contact: "", text: "" }));
                }}
              >
                <h3>Record what was received (Form 59)</h3>
                <div className="inline-form">
                  <label>
                    Kind
                    <select aria-label="Kind" value={comment.kind} onChange={(e) => setComment({ ...comment, kind: e.target.value })}>
                      {registry.data.comment_kinds.map((k) => (
                        <option key={k.code} value={k.code}>
                          {k.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    From
                    <input required aria-label="From" value={comment.name} onChange={(e) => setComment({ ...comment, name: e.target.value })} />
                  </label>
                  <label>
                    Phone or address
                    <input aria-label="Phone or address" value={comment.contact} onChange={(e) => setComment({ ...comment, contact: e.target.value })} />
                  </label>
                </div>
                <label>
                  What it says
                  <textarea required aria-label="What it says" rows={2} value={comment.text} onChange={(e) => setComment({ ...comment, text: e.target.value })} />
                </label>
                <div className="inline-form">
                  <button type="submit">Record it</button>
                </div>
              </form>
            )}
          </section>

          {canDecide && open && (
            <form
              className="card wide stack"
              aria-label="Decision"
              onSubmit={(e: FormEvent) => {
                e.preventDefault();
                void act(() => api.landDecide(item.id, approve ? { approve, conditions: terms } : { approve, reasons: terms }), "Decision recorded.");
              }}
            >
              <h2>Decision</h2>
              <div className="inline-form">
                <label>
                  The decision
                  <select aria-label="The decision" value={approve ? "approve" : "refuse"} onChange={(e) => setApprove(e.target.value === "approve")}>
                    <option value="approve">Approve</option>
                    <option value="refuse">Refuse</option>
                  </select>
                </label>
              </div>
              <label>
                {approve ? "Conditions (one per line)" : "Reasons for refusing (one per line)"}
                <textarea aria-label={approve ? "Conditions" : "Reasons"} required={!approve} rows={2} value={terms} onChange={(e) => setTerms(e.target.value)} />
              </label>
              <div className="inline-form">
                <button type="submit">Record the decision</button>
              </div>
              {item.kind === "rezoning" && item.status === "received" && (
                <div className="inline-form">
                  <label>
                    Or defer it, telling the applicant why (r.33(16): then decided within {registry.data.deferred_decision_days} days)
                    <input aria-label="Reason for deferring" value={deferReason} onChange={(e) => setDeferReason(e.target.value)} />
                  </label>
                  <button type="button" className="secondary" disabled={!deferReason.trim()} onClick={() => void act(() => api.landDefer(item.id, deferReason), "Decision deferred.")}>
                    Defer
                  </button>
                </div>
              )}
            </form>
          )}

          {item.kind === "rezoning" && item.status === "approved" && (
            <section aria-label="On the map" className="card wide">
              <h2>On the map</h2>
              {item.applied_on ? (
                <p>
                  The new zone ({item.proposed_zone}) was written to the parcels on {item.applied_on}.
                </p>
              ) : (
                <>
                  <p>The parcels still carry their old zone on the map.</p>
                  {canDecide && (
                    <button
                      type="button"
                      onClick={async () => {
                        setError(null);
                        try {
                          const done = await api.landApply(item.id);
                          setItem(done.application);
                          setNote(
                            `Zone written to ${done.written.parcels_changed} parcel(s).` +
                              (done.written.zoning_layer ? " This project also has a zoning layer: redraw the zone there too." : ""),
                          );
                        } catch (err) {
                          setError(err);
                        }
                      }}
                    >
                      Write {item.proposed_zone} to the map
                    </button>
                  )}
                </>
              )}
            </section>
          )}

          {canProcess && open && (
            <p>
              <button type="button" className="link" onClick={() => window.confirm("Withdraw this application?") && void act(() => api.landWithdraw(item.id), "Application withdrawn.")}>
                The applicant has withdrawn it
              </button>
            </p>
          )}
        </>
      )}
    </section>
  );
}
