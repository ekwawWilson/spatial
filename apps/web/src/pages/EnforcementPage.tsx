import type { CaseSummary, EnforcementCase, EnforcementNotice, EnforcementRegistry, NewCase } from "@spatial/map-core";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ErrorMessage } from "../components/ErrorMessage";
import { useLoad } from "../components/useLoad";
import { saveBlob } from "../components/workspace/ExportDialog";
import { useSession } from "../session";

function Next({ item }: { item: CaseSummary }) {
  const next = item.next_action;
  if (!next) return <span className="muted">—</span>;
  return (
    <span className={next.overdue ? "error" : undefined}>
      {next.label}
      {next.due_on && (next.overdue ? `: overdue since ${next.due_on}` : `: by ${next.due_on}`)}
    </span>
  );
}

function Detection({ projectId, canAct, onOpen }: { projectId: number; canAct: boolean; onOpen(): void }) {
  const { api, districtId } = useSession();
  const images = useLoad(() => api.listImagery(projectId), [api, projectId, districtId]);
  const runs = useLoad(() => api.listDetections(projectId), [api, projectId, districtId]);
  const [before, setBefore] = useState("");
  const [after, setAfter] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const ready = images.data?.filter((i) => i.kind === "ortho" && i.status === "ready") ?? [];
  const latest = runs.data?.results[0];

  async function compare(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await api.detectChanges(projectId, Number(before), Number(after));
      runs.reload();
      onOpen();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="Changes between images" className="card wide">
      <h2>Find new development from the air</h2>
      <p className="muted small">
        Compares two orthophotos of the same place and marks where the ground changed: each place is checked against granted permits
        and the buildings on the map. Light and season change pictures too, so each is a place to look, not a finding.
      </p>
      <ErrorMessage error={error ?? runs.error} />
      {ready.length < 2 ? (
        <p>
          Two orthophotos of the same area, taken at different times, are needed. <Link to={`/projects/${projectId}/imagery`}>Upload imagery</Link>.
        </p>
      ) : (
        canAct && (
          <form className="inline-form" aria-label="Compare two images" onSubmit={compare}>
            <label>
              Earlier image
              <select required aria-label="Earlier image" value={before} onChange={(e) => setBefore(e.target.value)}>
                <option value="">Choose…</option>
                {ready.map((i) => (
                  <option key={i.id} value={i.id}>
                    {i.name} ({i.capture_date ?? "no date"})
                  </option>
                ))}
              </select>
            </label>
            <label>
              Later image
              <select required aria-label="Later image" value={after} onChange={(e) => setAfter(e.target.value)}>
                <option value="">Choose…</option>
                {ready
                  .filter((i) => String(i.id) !== before)
                  .map((i) => (
                    <option key={i.id} value={i.id}>
                      {i.name} ({i.capture_date ?? "no date"})
                    </option>
                  ))}
              </select>
            </label>
            <button type="submit" disabled={busy || !before || !after}>
              {busy ? "Comparing…" : "Compare"}
            </button>
          </form>
        )
      )}
      {latest && (
        <div role="status">
          <p>
            Between <strong>{latest.before}</strong> and <strong>{latest.after}</strong>: {latest.found} place(s) changed.
          </p>
          <ul>
            <li className={latest.summary.new ? "error" : undefined}>
              {latest.summary.new} new: no permit and no building on the map
            </li>
            <li>{latest.summary.existing} at a building already on the map</li>
            <li>{latest.summary.permitted} where a permit has been granted</li>
          </ul>
          <p className="muted small">
            They are in the layer "Changes found between images" on <Link to={`/projects/${projectId}`}>the project's map</Link>, coloured by
            kind. Click one there to see its details, then open a case on it here with its feature number.
          </p>
        </div>
      )}
    </section>
  );
}

function OpenCase(props: { projectId: number; registry: EnforcementRegistry; onOpened(id: number): void; onCancel(): void }) {
  const { api } = useSession();
  const [values, setValues] = useState({ contravention: "no_permit", origin: "inspection", description: "", owner_name: "", owner_address: "", owner_contact: "", feature: "" });
  const [error, setError] = useState<unknown>(null);
  const set = (key: keyof typeof values, value: string) => setValues((v) => ({ ...v, [key]: value }));
  return (
    <form
      className="card wide stack"
      aria-label="Open a case"
      onSubmit={async (e: FormEvent) => {
        e.preventDefault();
        setError(null);
        const data: NewCase = { project: props.projectId, contravention: values.contravention, origin: values.origin as NewCase["origin"], description: values.description };
        if (values.owner_name) data.owner_name = values.owner_name;
        if (values.owner_address) data.owner_address = values.owner_address;
        if (values.owner_contact) data.owner_contact = values.owner_contact;
        if (values.feature) data.feature = Number(values.feature);
        try {
          props.onOpened((await api.openCase(data)).id);
        } catch (err) {
          setError(err);
        }
      }}
    >
      <h2>Open a case</h2>
      <ErrorMessage error={error} />
      <div className="inline-form">
        <label>
          Contravention
          <select aria-label="Contravention" value={values.contravention} onChange={(e) => set("contravention", e.target.value)}>
            {props.registry.contraventions.map((c) => (
              <option key={c.code} value={c.code}>
                {c.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          How it came to light
          <select aria-label="How it came to light" value={values.origin} onChange={(e) => set("origin", e.target.value)}>
            <option value="inspection">Found on inspection</option>
            <option value="complaint">Reported by the public</option>
            <option value="detection">Found by comparing images</option>
            <option value="check">Flagged by the standards check</option>
          </select>
        </label>
        <label>
          Feature number on the map (optional)
          <input type="number" min={1} aria-label="Feature number" style={{ width: "8rem" }} value={values.feature} onChange={(e) => set("feature", e.target.value)} />
        </label>
      </div>
      <label>
        What was found
        <textarea required aria-label="What was found" rows={2} value={values.description} onChange={(e) => set("description", e.target.value)} />
      </label>
      <div className="inline-form">
        <label>
          Owner or occupier
          <input aria-label="Owner or occupier" value={values.owner_name} onChange={(e) => set("owner_name", e.target.value)} />
        </label>
        <label>
          Address
          <input aria-label="Address" value={values.owner_address} onChange={(e) => set("owner_address", e.target.value)} />
        </label>
        <label>
          Phone or email
          <input aria-label="Phone or email" value={values.owner_contact} onChange={(e) => set("owner_contact", e.target.value)} />
        </label>
      </div>
      <div className="inline-form">
        <button type="submit">Open the case</button>
        <button type="button" className="link" onClick={props.onCancel}>
          Cancel
        </button>
      </div>
    </form>
  );
}

/** A project's enforcement cases, and the comparison of images that finds new ones. */
export function EnforcementPage() {
  const { projectId } = useParams();
  const id = Number(projectId);
  const navigate = useNavigate();
  const { api, can, districtId } = useSession();
  const registry = useLoad(() => api.enforcementRegistry(), [api]);
  const [status, setStatus] = useState("");
  const [opening, setOpening] = useState(false);
  const list = useLoad(() => api.listCases({ project: id, status: status || undefined }), [api, id, districtId, status]);
  const summary = list.data?.summary;

  return (
    <section className="page">
      <p>
        <Link to={`/projects/${id}`}>← Back to the project</Link>
      </p>
      <h1>Enforcement</h1>
      <p className="muted">
        Contraventions, the notices served for them, and the days the Regulations set between steps (Act 925 s.160–167; L.I. 2384
        r.55–58).
      </p>
      <ErrorMessage error={list.error ?? registry.error} />
      <Detection projectId={id} canAct={can("enforcement.act")} onOpen={() => undefined} />
      {summary && (
        <dl className="facts" aria-label="Summary">
          <dt>Open cases</dt>
          <dd>{summary.open}</dd>
          <dt>With a step overdue</dt>
          <dd className={summary.overdue ? "error" : undefined}>{summary.overdue}</dd>
        </dl>
      )}
      <div className="inline-form">
        <label>
          Show
          <select aria-label="Show" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All cases</option>
            <option value="open">Open</option>
            <option value="notice">Notice served</option>
            <option value="rectified">Rectified by the owner</option>
            <option value="enforced">Rectified by the Assembly</option>
            <option value="dropped">No contravention found</option>
          </select>
        </label>
        {can("enforcement.open") && !opening && registry.data && (
          <button type="button" onClick={() => setOpening(true)}>
            Open a case
          </button>
        )}
      </div>
      {opening && registry.data && <OpenCase projectId={id} registry={registry.data} onCancel={() => setOpening(false)} onOpened={(made) => navigate(`/projects/${id}/enforcement/${made}`)} />}
      {list.data?.results.length === 0 && <p>No cases {status ? "match" : "yet"}.</p>}
      {list.data && list.data.results.length > 0 && (
        <table className="data">
          <thead>
            <tr>
              <th>Case</th>
              <th>Contravention</th>
              <th>Opened</th>
              <th>Status</th>
              <th>Next</th>
            </tr>
          </thead>
          <tbody>
            {list.data.results.map((item) => (
              <tr key={item.id}>
                <td>
                  <Link to={`/projects/${id}/enforcement/${item.id}`}>{item.number}</Link>
                </td>
                <td>
                  {item.contravention_label}
                  <div className="muted small">{item.description}</div>
                </td>
                <td>{item.opened_on}</td>
                <td>{item.status_label}</td>
                <td>
                  <Next item={item} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function noticeFollows(notice: EnforcementNotice): string[] {
  const d = notice.dates;
  const lines: string[] = [];
  if (d.enforcement_notice_due_on) lines.push(`Not rectified in time: an enforcement notice is due by ${d.enforcement_notice_due_on} (r.57(2))${d.overdue ? ", now overdue" : ""}.`);
  if (d.assembly_may_act_from) lines.push(`If not complied with, the Assembly may rectify and recover the cost from ${d.assembly_may_act_from} (r.57(4)).`);
  if (d.entry_not_before) lines.push(`Entry not before ${d.entry_not_before} (r.58).`);
  if (d.show_cause_by) lines.push(`The permit holder has until ${d.show_cause_by} to show cause.`);
  return lines;
}

/** One enforcement case: its notices, how they were served, and how it ended. */
export function CasePage() {
  const { projectId, caseId } = useParams();
  const { api, can, districtId } = useSession();
  const loaded = useLoad(() => api.getCase(Number(caseId)), [api, caseId, districtId]);
  const registry = useLoad(() => api.enforcementRegistry(), [api]);
  const [item, setItem] = useState<EnforcementCase | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [note, setNote] = useState<string | null>(null);
  const [kind, setKind] = useState("rectification");
  const [grounds, setGrounds] = useState("");
  const [required, setRequired] = useState("");
  const [complyBy, setComplyBy] = useState("");
  const [method, setMethod] = useState<Record<number, string>>({});
  const [closing, setClosing] = useState<"rectified" | "enforced" | "dropped">("rectified");
  const [outcome, setOutcome] = useState("");
  const [cost, setCost] = useState("");
  const [recovered, setRecovered] = useState("");
  useEffect(() => setItem(loaded.data), [loaded.data]);

  const act = async (action: () => Promise<EnforcementCase>, done: string) => {
    setError(null);
    setNote(null);
    try {
      setItem(await action());
      setNote(done);
    } catch (err) {
      setError(err);
    }
  };
  const canAct = can("enforcement.act");
  const open = item !== null && (item.status === "open" || item.status === "notice");
  const spec = registry.data?.notices.find((n) => n.code === kind);

  return (
    <section className="page">
      <p>
        <Link to={`/projects/${projectId}/enforcement`}>← All cases</Link>
      </p>
      <ErrorMessage error={error ?? loaded.error ?? registry.error} />
      {note && <p role="status">{note}</p>}
      {item && registry.data && (
        <>
          <h1>
            {item.number} <span className="muted small">· {item.status_label}</span>
          </h1>
          <dl className="facts">
            <dt>Contravention</dt>
            <dd>
              {item.contravention_label} <span className="muted small">({item.section})</span>
            </dd>
            <dt>Found</dt>
            <dd>
              {item.description || "—"} <span className="muted small">{item.origin_label}, {item.opened_on}</span>
            </dd>
            {item.owner_name !== "restricted" && (
              <>
                <dt>Owner or occupier</dt>
                <dd>{[item.owner_name, item.owner_address, item.owner_contact].filter(Boolean).join(" · ") || "Not known"}</dd>
              </>
            )}
            {item.permit_number && (
              <>
                <dt>Permit</dt>
                <dd>{item.permit && <Link to={`/projects/${projectId}/permits/${item.permit}`}>{item.permit_number}</Link>}</dd>
              </>
            )}
            {item.next_action && (
              <>
                <dt>Next</dt>
                <dd>
                  <Next item={item} />
                </dd>
              </>
            )}
            {item.closed_on && (
              <>
                <dt>Closed</dt>
                <dd>
                  {item.closed_on}. {item.outcome}
                  {item.cost && ` Cost GHS ${item.cost}; recovered GHS ${item.cost_recovered ?? "0.00"}.`}
                </dd>
              </>
            )}
          </dl>

          <section aria-label="Notices" className="card wide">
            <h2>Notices</h2>
            {item.notices.length === 0 && <p>None issued yet.</p>}
            {item.notices.map((notice) => (
              <article key={notice.id} aria-label={notice.label} className="stack">
                <h3>
                  {notice.label} <span className="muted small">{notice.form ? `Form ${notice.form}, ` : ""}{notice.rule}</span>
                </h3>
                <p className="small">
                  Issued {notice.issued_on}
                  {notice.comply_by && `; to comply by ${notice.comply_by}`}
                  {notice.served_on ? `; served ${notice.served_on}: ${notice.served_by_label.toLowerCase()}${notice.served_note ? ` (${notice.served_note})` : ""}` : "; not served yet"}
                  {notice.complied_on && `; complied with on ${notice.complied_on}`}.
                </p>
                {noticeFollows(notice).map((line) => (
                  <p key={line} className={notice.dates.overdue ? "error small" : "small"}>
                    {line}
                  </p>
                ))}
                <div className="inline-form">
                  <button type="button" className="secondary" onClick={async () => saveBlob(await api.noticePaper(notice.id), `${notice.kind}-${item.number.replace(/\//g, "-")}.pdf`)}>
                    Download the notice
                  </button>
                  {canAct && open && !notice.served_on && (
                    <>
                      <label>
                        Served by
                        <select aria-label={`How the ${notice.label} was served`} value={method[notice.id] ?? "on_land"} onChange={(e) => setMethod({ ...method, [notice.id]: e.target.value })}>
                          {registry.data!.service_methods.map((m) => (
                            <option key={m.code} value={m.code}>
                              {m.label}
                            </option>
                          ))}
                        </select>
                      </label>
                      <button type="button" onClick={() => void act(() => api.serveNotice(notice.id, { method: method[notice.id] ?? "on_land" }), "Service recorded.")}>
                        Record service today
                      </button>
                    </>
                  )}
                  {canAct && open && notice.served_on && !notice.complied_on && notice.kind !== "entry" && (
                    <button type="button" className="secondary" onClick={() => void act(() => api.noticeComplied(notice.id), "Marked as complied with.")}>
                      Complied with
                    </button>
                  )}
                </div>
              </article>
            ))}
            {canAct && open && (
              <form
                className="stack"
                aria-label="Issue a notice"
                onSubmit={(e: FormEvent) => {
                  e.preventDefault();
                  void act(() => api.issueNotice(item.id, { kind, grounds, remedy: required, comply_by: complyBy || null }), "Notice issued. Download it, serve it, then record how it was served.").then(() => {
                    setGrounds("");
                    setRequired("");
                    setComplyBy("");
                  });
                }}
              >
                <h3>Issue a notice</h3>
                <div className="inline-form">
                  <label>
                    Notice
                    <select aria-label="Notice" value={kind} onChange={(e) => setKind(e.target.value)}>
                      {registry.data.notices.map((n) => (
                        <option key={n.code} value={n.code}>
                          {n.label}
                          {n.form && ` (Form ${n.form})`}
                        </option>
                      ))}
                    </select>
                  </label>
                  {spec?.dated && (
                    <label>
                      {kind === "entry" ? "Entry on or after (optional)" : "To comply by"}
                      <input type="date" aria-label="To comply by" value={complyBy} onChange={(e) => setComplyBy(e.target.value)} />
                    </label>
                  )}
                </div>
                <label>
                  What has come to the Assembly's attention (one point per line)
                  <textarea required aria-label="Grounds" rows={3} value={grounds} onChange={(e) => setGrounds(e.target.value)} />
                </label>
                <label>
                  What must be done (one point per line)
                  <textarea aria-label="What must be done" rows={2} value={required} onChange={(e) => setRequired(e.target.value)} />
                </label>
                <div className="inline-form">
                  <button type="submit">Issue the notice</button>
                </div>
              </form>
            )}
          </section>

          {canAct && open && (
            <form
              className="card wide stack"
              aria-label="Close the case"
              onSubmit={(e: FormEvent) => {
                e.preventDefault();
                void act(() => api.closeCase(item.id, { status: closing, outcome, cost: closing === "enforced" && cost ? cost : null, cost_recovered: closing === "enforced" && recovered ? recovered : null }), "Case closed.");
              }}
            >
              <h2>Close the case</h2>
              <div className="inline-form">
                <label>
                  How it ended
                  <select aria-label="How it ended" value={closing} onChange={(e) => setClosing(e.target.value as typeof closing)}>
                    <option value="rectified">Rectified by the owner</option>
                    <option value="enforced">Rectified by the Assembly (r.57(4))</option>
                    <option value="dropped">No contravention found</option>
                  </select>
                </label>
                {closing === "enforced" && (
                  <>
                    <label>
                      Cost (GHS)
                      <input type="number" min={0} step="0.01" aria-label="Cost" style={{ width: "8rem" }} value={cost} onChange={(e) => setCost(e.target.value)} />
                    </label>
                    <label>
                      Recovered so far (GHS)
                      <input type="number" min={0} step="0.01" aria-label="Recovered so far" style={{ width: "8rem" }} value={recovered} onChange={(e) => setRecovered(e.target.value)} />
                    </label>
                  </>
                )}
              </div>
              <label>
                What happened
                <textarea aria-label="What happened" rows={2} value={outcome} onChange={(e) => setOutcome(e.target.value)} />
              </label>
              <div className="inline-form">
                <button type="submit">Close the case</button>
              </div>
            </form>
          )}
        </>
      )}
    </section>
  );
}
