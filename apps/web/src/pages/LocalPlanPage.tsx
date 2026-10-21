import type { NewConsultation, PlanClock, PlanProcess } from "@spatial/map-core";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { ErrorMessage } from "../components/ErrorMessage";
import { useLoad } from "../components/useLoad";
import { saveBlob } from "../components/workspace/ExportDialog";
import { useSession } from "../session";

function when(clock: PlanClock): string {
  if (clock.done_on) return `Done ${clock.done_on}${clock.late ? `, late (due ${clock.due_on})` : ""}`;
  if (clock.due_on) return clock.overdue ? `Overdue since ${clock.due_on}` : `Due by ${clock.due_on}`;
  return clock.limit ? "Not started to run" : "No time set";
}

const BLANK: NewConsultation = { stage: "before", held_on: "", venue: "", groups: "", attendance: null, issues: "", outcome: "" };

/** The planning area's facilities against the national planning standards, for its population. */
function Facilities({ projectId }: { projectId: number }) {
  const { api, districtId } = useSession();
  const [population, setPopulation] = useState("");
  const [asked, setAsked] = useState<number | undefined>(undefined);
  const check = useLoad(() => api.facilityCheck(projectId, asked === undefined ? {} : { population: asked }), [api, projectId, districtId, asked]);
  const data = check.data;
  return (
    <section aria-label="Facilities against the standards" className="card wide">
      <h2>Facilities against the planning standards</h2>
      <p className="muted small">
        What a local plan specifies includes the basic social services the area needs (r.24(1)(b)). The national standards give one facility
        for so many people, and for schools and water a farthest walk from home.
      </p>
      <ErrorMessage error={check.error} />
      <form
        className="inline-form"
        aria-label="Population"
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          setAsked(population === "" ? undefined : Number(population));
        }}
      >
        <label>
          Population of the planning area
          <input aria-label="Population of the planning area" inputMode="numeric" placeholder={data?.population.value ? String(data.population.value) : ""} value={population} onChange={(e) => setPopulation(e.target.value)} />
        </label>
        <button type="submit" className="secondary">
          Check
        </button>
      </form>
      {data && (
        <p className="small">
          {data.population.value === null ? "Population unknown: give it above." : `${data.population.value.toLocaleString()} people (${data.population.source}).`}{" "}
          {data.facilities_layer ? `Facilities from the "${data.facilities_layer.name}" layer.` : "Say which layer holds the facilities (Relationships, Layers): until then nothing is counted."}
        </p>
      )}
      {data && data.results.length > 0 && (
        <table className="data" aria-label="Facilities">
          <thead>
            <tr>
              <th>Facility</th>
              <th>Standard</th>
              <th>Needed</th>
              <th>On the map</th>
              <th>Beyond walking distance</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data.results.map((r) => (
              <tr key={r.code}>
                <td>
                  {r.label}
                  <div className="muted small">§{r.section}</div>
                </td>
                <td className="small">
                  {[r.per && `1 per ${r.per.toLocaleString()} people`, r.walk_m && `within ${r.walk_m >= 1000 ? `${r.walk_m / 1000} km` : `${r.walk_m} m`}`, r.acres_need !== null && `${r.acres_need} acres`].filter(Boolean).join("; ") || "—"}
                </td>
                <td>{r.need ?? (r.acres_need !== null ? `${r.acres_need} acres` : "—")}</td>
                <td>{r.acres_have !== null ? `${r.have} (${r.acres_have} acres)` : r.have}</td>
                <td>{r.beyond === null ? "—" : data.homes ? `${r.beyond} of ${data.homes} buildings` : r.beyond}</td>
                <td>
                  <span className={`pill ${r.status === "short" ? "warn" : r.status === "met" ? "ok" : ""}`}>{r.status === "short" ? (r.short ? `${r.short} short` : "Short") : r.status === "met" ? "Met" : "—"}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {data && data.unclassified.length > 0 && (
        <p className="muted small">Not matched to a standard (check their type): {data.unclassified.map((u) => `${u.type} (${u.count})`).join(", ")}.</p>
      )}
      {data && <p className="muted small">{data.source}.</p>}
    </section>
  );
}

/** The making of a project's local plan: its steps and dates, what it covers, the consultations and the comments. */
export function LocalPlanPage() {
  const { projectId } = useParams();
  const id = Number(projectId);
  const { api, can, districtId } = useSession();
  const loaded = useLoad(() => api.getPlanProcess(id), [api, id, districtId]);
  const [plan, setPlan] = useState<PlanProcess | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [note, setNote] = useState<string | null>(null);
  const [settings, setSettings] = useState({ origin: "committee", prepared_by: "", structure_plan_on: "", application_on: "", conditions: "", valid_until: "" });
  const [stepNote, setStepNote] = useState<Record<string, string>>({});
  const [covered, setCovered] = useState<Record<string, { covered: boolean; note: string }>>({});
  const [meeting, setMeeting] = useState<NewConsultation>(BLANK);
  const [comment, setComment] = useState({ name: "", contact: "", topic: "", text: "" });
  const [reply, setReply] = useState<Record<number, string>>({});

  function show(next: PlanProcess) {
    setPlan(next);
    setSettings({
      origin: next.origin,
      prepared_by: next.prepared_by,
      structure_plan_on: next.structure_plan_on ?? "",
      application_on: next.application_on ?? "",
      conditions: next.conditions,
      valid_until: next.valid_until ?? "",
    });
    setCovered(Object.fromEntries(next.content.map((i) => [i.code, { covered: i.covered, note: i.note }])));
  }
  useEffect(() => {
    if (loaded.data) show(loaded.data);
  }, [loaded.data]);

  const act = async (action: () => Promise<PlanProcess>, done: string) => {
    setError(null);
    setNote(null);
    try {
      show(await action());
      setNote(done);
      return true;
    } catch (err) {
      setError(err);
      return false;
    }
  };
  const canEdit = can("project.edit");
  const canDecide = can("permit.decide");

  return (
    <section className="page">
      <p>
        <Link to={`/projects/${id}`}>← Back to the project</Link>
      </p>
      <h1>Local plan</h1>
      <p className="muted">
        The making of this project's local plan, by the steps and time limits of the Regulations (L.I. 2384 r.23–27), with the public
        consultations held for it (r.65) and the comments on the draft.
      </p>
      <ErrorMessage error={error ?? loaded.error} />
      {note && <p role="status">{note}</p>}
      {plan && (
        <>
          <form
            className="card wide stack"
            aria-label="About the plan"
            onSubmit={(e: FormEvent) => {
              e.preventDefault();
              void act(
                () =>
                  api.updatePlanProcess(id, {
                    origin: settings.origin as "committee" | "applicant",
                    prepared_by: settings.prepared_by,
                    structure_plan_on: settings.structure_plan_on || null,
                    application_on: settings.application_on || null,
                    conditions: settings.conditions,
                    valid_until: settings.valid_until || null,
                  }),
                "Saved.",
              );
            }}
          >
            <h2>About the plan</h2>
            <div className="inline-form">
              <label>
                Prepared by
                <select aria-label="Prepared by" disabled={!canEdit} value={settings.origin} onChange={(e) => setSettings({ ...settings, origin: e.target.value })}>
                  <option value="committee">The District Spatial Planning Committee</option>
                  <option value="applicant">Another person, for the Assembly's approval</option>
                </select>
              </label>
              <label>
                Name of who prepared it
                <input aria-label="Name of who prepared it" disabled={!canEdit} value={settings.prepared_by} onChange={(e) => setSettings({ ...settings, prepared_by: e.target.value })} />
              </label>
            </div>
            <div className="inline-form">
              <label>
                Structure plan in force since
                <input type="date" aria-label="Structure plan in force since" disabled={!canEdit} value={settings.structure_plan_on} onChange={(e) => setSettings({ ...settings, structure_plan_on: e.target.value })} />
              </label>
              {settings.origin === "applicant" && (
                <label>
                  Application for approval received
                  <input type="date" aria-label="Application for approval received" disabled={!canEdit} value={settings.application_on} onChange={(e) => setSettings({ ...settings, application_on: e.target.value })} />
                </label>
              )}
              <label>
                Plan valid until
                <input type="date" aria-label="Plan valid until" disabled={!canEdit} value={settings.valid_until} onChange={(e) => setSettings({ ...settings, valid_until: e.target.value })} />
              </label>
            </div>
            <label>
              Conditions imposed (r.27), one per line
              <textarea aria-label="Conditions imposed" rows={2} disabled={!canEdit} value={settings.conditions} onChange={(e) => setSettings({ ...settings, conditions: e.target.value })} />
            </label>
            <p className="muted small">The Committee may impose: {plan.possible_conditions.map((c) => c.toLowerCase()).join("; ")}.</p>
            {canEdit && (
              <div className="inline-form">
                <button type="submit">Save</button>
              </div>
            )}
          </form>

          <section aria-label="Steps and deadlines" className="card wide">
            <h2>Steps and deadlines</h2>
            {plan.comments_close_on && (
              <p className={plan.comments_open ? undefined : "muted"}>
                The public {plan.comments_open ? "may comment" : "could comment"} on the draft until <strong>{plan.comments_close_on}</strong>{" "}
                <span className="muted small">
                  ({plan.comment_days} days, {plan.comment_rule}). The plan cannot be approved before then.
                </span>
              </p>
            )}
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
                {plan.clocks.map((clock) => (
                  <tr key={clock.code}>
                    <td>
                      {clock.label}
                      {clock.form && <span className="muted small"> (Form {clock.form})</span>}
                      {clock.note && <div className="muted small">{clock.note}</div>}
                    </td>
                    <td className="small">
                      {clock.rule}
                      {clock.limit && `: ${clock.limit}`}
                    </td>
                    <td className={clock.overdue || clock.late ? "error" : undefined}>{when(clock)}</td>
                    <td>
                      {!clock.done_on && (clock.decision ? canDecide : canEdit) && (
                        <span className="inline-form">
                          <input aria-label={`Note for: ${clock.label}`} placeholder="Note" value={stepNote[clock.code] ?? ""} onChange={(e) => setStepNote({ ...stepNote, [clock.code]: e.target.value })} />
                          <button type="button" className="secondary" aria-label={`Done today: ${clock.label}`} onClick={() => void act(() => api.planStep(id, { step: clock.code, note: stepNote[clock.code] ?? "" }), "Step recorded.")}>
                            Done today
                          </button>
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="inline-form">
              {plan.papers.map((paper) => (
                <button key={paper.code} type="button" className="secondary" onClick={async () => saveBlob(await api.planPaper(id, paper.code), `${paper.code}-plan-${id}.pdf`)}>
                  Download: {paper.label}
                </button>
              ))}
            </div>
          </section>

          <form
            className="card wide stack"
            aria-label="What the plan specifies"
            onSubmit={(e: FormEvent) => {
              e.preventDefault();
              void act(() => api.planContent(id, covered), "Saved.");
            }}
          >
            <h2>
              What the plan specifies{" "}
              <span className="muted small">
                {plan.content_covered} of {plan.content.length} ({plan.content_rule})
              </span>
            </h2>
            {plan.content.map((item) => (
              <div key={item.code} className="inline-form">
                <label className="checkbox">
                  <input
                    type="checkbox"
                    disabled={!canEdit}
                    checked={covered[item.code]?.covered ?? false}
                    onChange={(e) => setCovered({ ...covered, [item.code]: { covered: e.target.checked, note: covered[item.code]?.note ?? "" } })}
                  />{" "}
                  ({item.code}) {item.label}
                </label>
                <input
                  aria-label={`Where the plan covers: ${item.label}`}
                  placeholder="Where in the plan, or why not"
                  disabled={!canEdit}
                  value={covered[item.code]?.note ?? ""}
                  onChange={(e) => setCovered({ ...covered, [item.code]: { covered: covered[item.code]?.covered ?? false, note: e.target.value } })}
                />
              </div>
            ))}
            {canEdit && (
              <div className="inline-form">
                <button type="submit">Save what it covers</button>
              </div>
            )}
          </form>

          <Facilities projectId={id} />

          <section aria-label="Consultations" className="card wide">
            <h2>Consultations</h2>
            <p className="muted small">Minutes of each consultation are recorded and a copy displayed in the Public Data Room (r.65).</p>
            {plan.consultations.length === 0 && <p className="muted">None recorded.</p>}
            {plan.consultations.map((c) => (
              <article key={c.id} className="stack">
                <p>
                  <strong>
                    {c.held_on}, {c.venue}
                  </strong>{" "}
                  <span className="muted small">
                    {c.stage_label}
                    {c.attendance !== null && `; ${c.attendance} attending`}
                    {c.groups && `; ${c.groups}`}
                  </span>
                </p>
                <p>{c.issues}</p>
                {c.outcome && <p className="small">Agreed: {c.outcome}</p>}
                <div className="inline-form">
                  <button type="button" className="secondary" onClick={async () => saveBlob(await api.consultationMinutes(c.id), `minutes-${c.held_on}.pdf`)}>
                    Download the minutes
                  </button>
                  {c.displayed_on ? (
                    <span className="muted small">On display in the Public Data Room since {c.displayed_on}</span>
                  ) : (
                    canEdit && (
                      <button type="button" aria-label={`Display the minutes of ${c.held_on}`} onClick={() => void act(() => api.displayConsultation(c.id), "The minutes are on display.")}>
                        Display in the Public Data Room
                      </button>
                    )
                  )}
                </div>
              </article>
            ))}
            {canEdit && (
              <form
                className="stack"
                aria-label="Record a consultation"
                onSubmit={(e: FormEvent) => {
                  e.preventDefault();
                  void act(() => api.recordConsultation(id, meeting), "Consultation recorded.").then((ok) => ok && setMeeting(BLANK));
                }}
              >
                <h3>Record a consultation</h3>
                <div className="inline-form">
                  <label>
                    When
                    <select aria-label="Stage" value={meeting.stage} onChange={(e) => setMeeting({ ...meeting, stage: e.target.value })}>
                      {plan.stages.map((s) => (
                        <option key={s.code} value={s.code}>
                          {s.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Held on
                    <input required type="date" aria-label="Held on" value={meeting.held_on} onChange={(e) => setMeeting({ ...meeting, held_on: e.target.value })} />
                  </label>
                  <label>
                    Venue
                    <input required aria-label="Venue" value={meeting.venue} onChange={(e) => setMeeting({ ...meeting, venue: e.target.value })} />
                  </label>
                  <label>
                    Number attending
                    <input type="number" min={0} aria-label="Number attending" style={{ width: "6rem" }} value={meeting.attendance ?? ""} onChange={(e) => setMeeting({ ...meeting, attendance: e.target.value === "" ? null : Number(e.target.value) })} />
                  </label>
                </div>
                <label>
                  Those consulted
                  <input aria-label="Those consulted" value={meeting.groups} onChange={(e) => setMeeting({ ...meeting, groups: e.target.value })} placeholder="e.g. chiefs, land owners, market traders, utilities" />
                </label>
                <label>
                  Issues raised
                  <textarea required aria-label="Issues raised" rows={3} value={meeting.issues} onChange={(e) => setMeeting({ ...meeting, issues: e.target.value })} />
                </label>
                <label>
                  Responses and what was agreed
                  <textarea aria-label="What was agreed" rows={2} value={meeting.outcome} onChange={(e) => setMeeting({ ...meeting, outcome: e.target.value })} />
                </label>
                <div className="inline-form">
                  <button type="submit">Record the consultation</button>
                </div>
              </form>
            )}
          </section>

          <section aria-label="Comments on the draft" className="card wide">
            <h2>
              Comments on the draft{" "}
              {plan.comments.length > 0 && (
                <span className={plan.comments_unanswered ? "error small" : "muted small"}>
                  {plan.comments_unanswered} of {plan.comments.length} not yet answered
                </span>
              )}
            </h2>
            {plan.comments.length === 0 && <p className="muted">None received.</p>}
            {plan.comments.map((c) => (
              <article key={c.id} className="stack">
                <p>
                  <strong>{c.received_on}</strong>
                  {c.name !== "restricted" && `, ${c.name}`}
                  {c.online && <span className="muted small"> (sent online)</span>}
                  {c.topic_label && <span className="muted small"> on {c.topic_label.toLowerCase()}</span>}: {c.text}
                </p>
                {c.response ? (
                  <p className="small">
                    The Committee's response ({c.responded_on}): {c.response}
                  </p>
                ) : (
                  canEdit && (
                    <span className="inline-form">
                      <input aria-label={`Response to comment ${c.id}`} placeholder="The Committee's response" value={reply[c.id] ?? ""} onChange={(e) => setReply({ ...reply, [c.id]: e.target.value })} />
                      <button type="button" className="secondary" disabled={!reply[c.id]} onClick={() => void act(() => api.replyPlanComment(c.id, reply[c.id] ?? ""), "Response recorded.")}>
                        Record the response
                      </button>
                    </span>
                  )
                )}
              </article>
            ))}
            {canEdit && (
              <form
                className="stack"
                aria-label="Record a comment"
                onSubmit={(e: FormEvent) => {
                  e.preventDefault();
                  void act(() => api.recordPlanComment(id, { name: comment.name, text: comment.text, contact: comment.contact || undefined, topic: comment.topic || undefined }), "Comment recorded.").then(
                    (ok) => ok && setComment({ name: "", contact: "", topic: "", text: "" }),
                  );
                }}
              >
                <h3>Record a comment received at the office (Form 59)</h3>
                <div className="inline-form">
                  <label>
                    From
                    <input required aria-label="From" value={comment.name} onChange={(e) => setComment({ ...comment, name: e.target.value })} />
                  </label>
                  <label>
                    Phone or address
                    <input aria-label="Phone or address" value={comment.contact} onChange={(e) => setComment({ ...comment, contact: e.target.value })} />
                  </label>
                  <label>
                    About
                    <select aria-label="About" value={comment.topic} onChange={(e) => setComment({ ...comment, topic: e.target.value })}>
                      <option value="">The plan as a whole</option>
                      {plan.content.map((i) => (
                        <option key={i.code} value={i.code}>
                          {i.label}
                        </option>
                      ))}
                    </select>
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
        </>
      )}
    </section>
  );
}
