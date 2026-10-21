import type { PermitApplication, PermitClock, PermitDecision, PermitRegistry } from "@spatial/map-core";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";

import { ErrorMessage } from "../components/ErrorMessage";
import { OfficerPicker } from "../components/OfficerPicker";
import { useLoad } from "../components/useLoad";
import { saveBlob } from "../components/workspace/ExportDialog";
import { useSession } from "../session";
import { OUTCOME } from "./PermitsPage";

const EVENTS: Record<string, string> = {
  received: "Received",
  acknowledged: "Receipt acknowledged",
  inspected: "Site inspected",
  completion: "Completed development inspected",
  reported: "Report sent to the Spatial Planning Committee",
  granted: "Granted",
  refused: "Refused",
  deferred: "Deferred",
  processing_fee_paid: "Processing fee paid",
  permit_fee_paid: "Permit fee paid",
  issued: "Permit issued",
  habitation: "Certificate of Habitation issued",
  withdrawn: "Withdrawn",
};
const DECISIONS: Record<PermitDecision, string> = { grant: "Grant", refuse: "Refuse", defer: "Defer" };

function clockState(clock: PermitClock): string {
  if (clock.done_on) return clock.late ? `done on ${clock.done_on}, late (due ${clock.due_on})` : `done on ${clock.done_on}`;
  return clock.overdue ? `overdue since ${clock.due_on}` : `due by ${clock.due_on}`;
}

function Card(props: { title: string; label?: string; children: ReactNode }) {
  return (
    <section aria-label={props.label ?? props.title} className="card wide">
      <h2>{props.title}</h2>
      {props.children}
    </section>
  );
}

type Act = (action: () => Promise<PermitApplication>, done?: string) => Promise<void>;

const BODIES: Record<"review" | "appeal", [string, string][]> = {
  review: [["assembly", "The District Assembly"]],
  appeal: [
    ["rcc", "The Regional Coordinating Council"],
    ["luspa", "The Land Use and Spatial Planning Authority"],
  ],
};
const OUTCOMES: [string, string][] = [
  ["upheld", "Decision upheld"],
  ["varied", "Decision varied"],
  ["overturned", "Decision overturned"],
  ["withdrawn", "Withdrawn"],
];

/** Requests for review (r.62, Form 53) and appeals (r.63, Form 54) against the decision. */
function Challenges({ permit, act }: { permit: PermitApplication; act: Act }) {
  const { api, can } = useSession();
  const reviewed = permit.challenges.some((c) => c.kind === "review");
  const [kind, setKind] = useState<"review" | "appeal">("review");
  const [body, setBody] = useState("assembly");
  const [grounds, setGrounds] = useState("");
  const [outcome, setOutcome] = useState<Record<number, string>>({});
  const [decision, setDecision] = useState<Record<number, string>>({});
  return (
    <Card title="Review and appeal" label="Review and appeal">
      <p className="muted small">
        A request for review goes to the District Assembly (Form 53, r.62); an appeal against its decision to the Regional Coordinating Council,
        and against the Council's to the Authority (Form 54, r.63). Each is decided and served within 21 days.
      </p>
      {permit.challenges.length === 0 && <p className="muted">None lodged.</p>}
      {permit.challenges.map((c) => (
        <article key={c.id} className="stack">
          <p>
            <strong>
              {c.kind_label} (Form {c.form}, {c.rule})
            </strong>{" "}
            to {c.body_label.toLowerCase()}, lodged {c.lodged_on}
            {c.clock.lodged_late && <span className="error"> (after the {c.clock.lodge_by} limit)</span>}: {c.grounds}
          </p>
          {c.decided_on ? (
            <p className={c.clock.late ? "error small" : "small"}>
              {c.outcome_label} on {c.decided_on}
              {c.decision && `: ${c.decision}`}
              {c.clock.late && ` (due by ${c.clock.decide_by})`}
            </p>
          ) : (
            <>
              <p className={c.clock.overdue ? "error small" : "muted small"}>Decision due by {c.clock.decide_by}.</p>
              {can("permit.decide") && (
                <div className="inline-form">
                  <label>
                    Outcome
                    <select aria-label={`Outcome of the ${c.kind}`} value={outcome[c.id] ?? "upheld"} onChange={(e) => setOutcome({ ...outcome, [c.id]: e.target.value })}>
                      {OUTCOMES.map(([code, label]) => (
                        <option key={code} value={code}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Decision
                    <input aria-label={`Decision on the ${c.kind}`} value={decision[c.id] ?? ""} onChange={(e) => setDecision({ ...decision, [c.id]: e.target.value })} />
                  </label>
                  <button type="button" onClick={() => void act(() => api.decideChallenge(permit.id, { challenge: c.id, outcome: outcome[c.id] ?? "upheld", decision: decision[c.id] ?? "" }), "Decision recorded.")}>
                    Record the decision
                  </button>
                </div>
              )}
            </>
          )}
        </article>
      ))}
      {can("permit.process") && (
        <form
          className="stack"
          aria-label="Lodge a review or appeal"
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            void act(() => api.lodgeChallenge(permit.id, { kind, body, grounds }), kind === "review" ? "Request for review recorded." : "Appeal recorded.").then(() => setGrounds(""));
          }}
        >
          <div className="inline-form">
            <label>
              Lodge
              <select
                aria-label="Lodge"
                value={kind}
                onChange={(e) => {
                  const next = e.target.value as "review" | "appeal";
                  setKind(next);
                  setBody(BODIES[next][0]![0]);
                }}
              >
                <option value="review">A request for review (Form 53)</option>
                <option value="appeal" disabled={!reviewed}>
                  An appeal (Form 54){reviewed ? "" : ": after a review"}
                </option>
              </select>
            </label>
            <label>
              To
              <select aria-label="To" value={body} onChange={(e) => setBody(e.target.value)}>
                {BODIES[kind].map(([code, label]) => (
                  <option key={code} value={code}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label>
            Grounds
            <textarea required aria-label="Grounds" rows={2} value={grounds} onChange={(e) => setGrounds(e.target.value)} />
          </label>
          <div className="inline-form">
            <button type="submit">Record it</button>
          </div>
        </form>
      )}
    </Card>
  );
}

function Inspection({ permit, registry, act }: { permit: PermitApplication; registry: PermitRegistry; act: Act }) {
  const { api } = useSession();
  const [findings, setFindings] = useState<Record<string, string>>({});
  const [summary, setSummary] = useState("");
  return (
    <form
      className="stack"
      aria-label="Site inspection"
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        void act(() => api.inspectPermit(permit.id, { findings, summary }), "Site inspection recorded.");
      }}
    >
      <h3>Record the site inspection (r.44(7)(f))</h3>
      {registry.inspection_points.map((point) => (
        <label key={point.code}>
          {point.label}
          <input aria-label={point.label} value={findings[point.code] ?? ""} onChange={(e) => setFindings({ ...findings, [point.code]: e.target.value })} />
        </label>
      ))}
      <label>
        Summary
        <textarea aria-label="Inspection summary" rows={2} value={summary} onChange={(e) => setSummary(e.target.value)} />
      </label>
      <div className="inline-form">
        <button type="submit">Record the inspection</button>
      </div>
    </form>
  );
}

function NextStep({ permit, registry, act }: { permit: PermitApplication; registry: PermitRegistry; act: Act }) {
  const { api, can } = useSession();
  const [recommendation, setRecommendation] = useState<PermitDecision>("grant");
  const [decision, setDecision] = useState<PermitDecision>(permit.recommendation || "grant");
  const [text, setText] = useState("");
  const [conditions, setConditions] = useState("");
  const [amount, setAmount] = useState("");
  const [receipt, setReceipt] = useState("");
  useEffect(() => setText(""), [permit.status]);
  const paper = async (kind: "acknowledgement" | "letter" | "certificate" | "habitation-certificate") => saveBlob(await api.permitPaper(permit.id, kind), `${kind}-${permit.number.replace(/\//g, "-")}.pdf`);
  const process = can("permit.process");

  if (permit.status === "received") {
    return (
      <Card title="Next: acknowledge receipt" label="Next step">
        <p>The Regulations ask for a written acknowledgement within 7 days (r.44(6)). The application then goes to the Technical Sub-Committee.</p>
        {process && (
          <button type="button" onClick={() => void act(() => api.acknowledgePermit(permit.id), "Receipt acknowledged. Download the acknowledgement for the applicant.")}>
            Acknowledge receipt
          </button>
        )}
      </Card>
    );
  }
  if (permit.status === "review" || permit.status === "deferred") {
    return (
      <Card title={permit.status === "deferred" ? "Deferred: look at it again" : "Next: the Technical Sub-Committee's inspection and report"} label="Next step">
        <div className="inline-form">
          <button type="button" className="secondary" onClick={() => void paper("acknowledgement")}>
            Download the acknowledgement
          </button>
          {permit.status === "deferred" && (
            <button type="button" className="secondary" onClick={() => void paper("letter")}>
              Download the deferral letter
            </button>
          )}
        </div>
        {can("permit.inspect") && <Inspection permit={permit} registry={registry} act={act} />}
        {process && (
          <form
            className="stack"
            aria-label="Report"
            onSubmit={(e: FormEvent) => {
              e.preventDefault();
              void act(() => api.reportPermit(permit.id, { recommendation, report: text }), "Report sent to the Spatial Planning Committee.");
            }}
          >
            <h3>Send the report to the Spatial Planning Committee (r.44(8))</h3>
            {!permit.inspected_on && <p className="muted small">Record the site inspection first.</p>}
            <label>
              Recommendation
              <select aria-label="Recommendation" value={recommendation} onChange={(e) => setRecommendation(e.target.value as PermitDecision)}>
                {Object.entries(DECISIONS).map(([code, label]) => (
                  <option key={code} value={code}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Findings and recommendation
              <textarea aria-label="Findings and recommendation" rows={3} value={text} onChange={(e) => setText(e.target.value)} />
            </label>
            <div className="inline-form">
              <button type="submit" disabled={!permit.inspected_on}>
                Send the report
              </button>
            </div>
          </form>
        )}
      </Card>
    );
  }
  if (permit.status === "reported") {
    return (
      <Card title="Next: the Spatial Planning Committee's decision" label="Next step">
        <p>
          The Technical Sub-Committee recommends: <strong>{permit.recommendation ? DECISIONS[permit.recommendation] : "—"}</strong>. {permit.report}
        </p>
        <p className="muted small">The committee considers: {registry.considerations.join("; ").toLowerCase()} (r.44(2), r.45(4)).</p>
        {can("permit.decide") ? (
          <form
            className="stack"
            aria-label="Decision"
            onSubmit={(e: FormEvent) => {
              e.preventDefault();
              void act(() => api.decidePermit(permit.id, { decision, reasons: text, conditions }), "Decision recorded.");
            }}
          >
            <label>
              Decision
              <select aria-label="Decision" value={decision} onChange={(e) => setDecision(e.target.value as PermitDecision)}>
                {Object.entries(DECISIONS).map(([code, label]) => (
                  <option key={code} value={code}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            {decision === "grant" ? (
              <label>
                Conditions
                <textarea aria-label="Conditions" rows={2} value={conditions} onChange={(e) => setConditions(e.target.value)} />
              </label>
            ) : (
              <label>
                Reasons (written to the applicant, r.44(13))
                <textarea required aria-label="Reasons" rows={3} value={text} onChange={(e) => setText(e.target.value)} />
              </label>
            )}
            <div className="inline-form">
              <button type="submit">Record the decision</button>
            </div>
          </form>
        ) : (
          <p className="muted">The district administrator records the committee's decision.</p>
        )}
      </Card>
    );
  }
  if (permit.status === "granted") {
    return (
      <Card title="Next: the permit fee, then the certificate" label="Next step">
        <p>Granted on {permit.decided_on}. The certificate is issued once the permit fee is paid (r.44(11)); the Regulations give 30 days from receipt.</p>
        {permit.permit_paid_on ? (
          <p>
            Permit fee: GHS {permit.permit_fee}, receipt {permit.permit_receipt}, paid {permit.permit_paid_on}.
          </p>
        ) : (
          process && (
            <form
              className="inline-form"
              aria-label="Permit fee receipt"
              onSubmit={(e: FormEvent) => {
                e.preventDefault();
                void act(() => api.recordPermitFee(permit.id, { stage: "permit", amount, receipt }), "Permit fee recorded.");
              }}
            >
              <label>
                Permit fee (GHS)
                <input required type="number" min={0} step="0.01" aria-label="Permit fee" style={{ width: "8rem" }} value={amount} onChange={(e) => setAmount(e.target.value)} />
              </label>
              <label>
                Receipt number
                <input required aria-label="Receipt number" value={receipt} onChange={(e) => setReceipt(e.target.value)} />
              </label>
              <button type="submit">Record the receipt</button>
            </form>
          )
        )}
        {can("permit.decide") && (
          <button type="button" disabled={!permit.permit_paid_on} onClick={() => void act(() => api.issuePermit(permit.id), "Permit issued. Download the certificate.")}>
            Issue the permit
          </button>
        )}
      </Card>
    );
  }
  if (permit.status === "issued") {
    return (
      <Card title={permit.expired ? "Permit expired" : "Permit issued"} label="Next step">
        <p>
          Issued on {permit.issued_on}; valid until {permit.expires_on}. If the development isn't finished by then, the permit must be renewed.
        </p>
        {can("permit.decide") && (
          <div className="inline-form">
            <button type="button" className="secondary" onClick={() => void act(() => api.renewPermit(permit.id), "Permit renewed for five more years.")}>
              Renew the permit (Spatial Planning Committee)
            </button>
          </div>
        )}
        <div className="inline-form">
          <button type="button" onClick={() => void paper("certificate")}>
            Download the certificate
          </button>
          {permit.verify_url && (
            <a href={permit.verify_url} target="_blank" rel="noreferrer">
              What the QR code shows
            </a>
          )}
        </div>
        {permit.kind === "development" && (
          <>
            <h3>When the development is finished: the Certificate of Habitation (r.45(15)–(18))</h3>
            {permit.habitation_on ? (
              <div className="inline-form">
                <span>Issued on {permit.habitation_on}.</span>
                <button type="button" onClick={() => void paper("habitation-certificate")}>
                  Download the Certificate of Habitation
                </button>
              </div>
            ) : permit.completion ? (
              <div className="inline-form">
                <span className={permit.completion.overdue ? "error" : undefined}>
                  Inspected on {permit.completion.inspected_on}: the certificate is due by {permit.completion.due_on}.
                </span>
                {can("permit.decide") && (
                  <button type="button" onClick={() => void act(() => api.certifyHabitation(permit.id), "Certificate of Habitation issued.")}>
                    Issue the Certificate of Habitation
                  </button>
                )}
              </div>
            ) : (
              can("permit.inspect") && (
                <form
                  className="inline-form"
                  aria-label="Completion inspection"
                  onSubmit={(e: FormEvent) => {
                    e.preventDefault();
                    void act(() => api.inspectPermit(permit.id, { purpose: "completion", findings: {}, summary: text }), "Completion inspection recorded.");
                  }}
                >
                  <label>
                    What the inspection of the finished development found
                    <input required aria-label="Completion inspection findings" value={text} onChange={(e) => setText(e.target.value)} />
                  </label>
                  <button type="submit">Record the completion inspection</button>
                </form>
              )
            )}
          </>
        )}
      </Card>
    );
  }
  if (permit.status === "refused") {
    return (
      <Card title="Refused" label="Next step">
        <p>Refused on {permit.decided_on}. The applicant may ask for a review within 30 days.</p>
        <button type="button" onClick={() => void paper("letter")}>
          Download the refusal letter
        </button>
      </Card>
    );
  }
  return (
    <Card title="Withdrawn" label="Next step">
      <p>This application was withdrawn.</p>
    </Card>
  );
}

function Documents({ permit, registry, act, canEdit }: { permit: PermitApplication; registry: PermitRegistry; act: Act; canEdit: boolean }) {
  const { api } = useSession();
  const [requirement, setRequirement] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const labelOf = (code: string) => registry.requirements.find((r) => r.code === code)?.label ?? "Other document";
  return (
    <Card title="Documents">
      <table className="data">
        <thead>
          <tr>
            <th>Required with this application</th>
            <th>Rule</th>
            <th>Submitted</th>
          </tr>
        </thead>
        <tbody>
          {permit.requirements.map((r) => (
            <tr key={r.code}>
              <td>
                {r.label}
                {r.asked_for && <span className="muted small"> (asked for by the officer)</span>}
              </td>
              <td className="small">{r.rule}</td>
              <td className={r.submitted ? undefined : "error"}>{r.submitted ? `${r.submitted}` : "missing"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {permit.documents.length > 0 && (
        <ul>
          {permit.documents.map((d) => (
            <li key={d.id}>
              <button type="button" className="link" onClick={async () => saveBlob(await api.downloadPermitDocument(d.id), d.name)}>
                {d.name}
              </button>{" "}
              <span className="muted small">{labelOf(d.requirement)}</span>{" "}
              {canEdit && (
                <button
                  type="button"
                  className="link"
                  aria-label={`Remove ${d.name}`}
                  onClick={() =>
                    void act(async () => {
                      await api.deletePermitDocument(d.id);
                      return api.getPermit(permit.id);
                    })
                  }
                >
                  Remove
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {canEdit && (
        <form
          className="inline-form"
          aria-label="Add a document"
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            if (!file) return;
            void act(() => api.uploadPermitDocument(permit.id, file, requirement), "Document added.");
            (e.target as HTMLFormElement).reset();
            setFile(null);
          }}
        >
          <label>
            Document
            <input type="file" aria-label="Document file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </label>
          <label>
            It is the
            <select aria-label="Document kind" value={requirement} onChange={(e) => setRequirement(e.target.value)}>
              <option value="">Other document</option>
              {registry.requirements.map((r) => (
                <option key={r.code} value={r.code}>
                  {r.label}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" disabled={!file}>
            Add
          </button>
        </form>
      )}
    </Card>
  );
}

function Comments({ permit, act, canEdit }: { permit: PermitApplication; act: Act; canEdit: boolean }) {
  const { api } = useSession();
  const [agency, setAgency] = useState("");
  const [body, setBody] = useState("");
  const [objection, setObjection] = useState(false);
  return (
    <Card title="Comments from departments and agencies">
      <p className="muted small">The application is circulated to the Works Department and other institutions for review (r.44(7)(d)).</p>
      {permit.comments.length === 0 && <p>None recorded.</p>}
      <ul>
        {permit.comments.map((c) => (
          <li key={c.id}>
            <strong>{c.agency}</strong>
            {c.objection && <span className="error"> (objects)</span>}: {c.body}
          </li>
        ))}
      </ul>
      {canEdit && (
        <form
          className="inline-form"
          aria-label="Add a comment"
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            void act(() => api.commentOnPermit(permit.id, { agency, body, objection }), "Comment recorded.");
            setBody("");
          }}
        >
          <label>
            From
            <input required aria-label="Agency" value={agency} onChange={(e) => setAgency(e.target.value)} placeholder="e.g. Works Department" />
          </label>
          <label>
            Comment
            <input required aria-label="Comment" value={body} onChange={(e) => setBody(e.target.value)} />
          </label>
          <label className="checkbox">
            <input type="checkbox" checked={objection} onChange={(e) => setObjection(e.target.checked)} /> An objection
          </label>
          <button type="submit">Record</button>
        </form>
      )}
    </Card>
  );
}

/** One permit application: where it stands, what is due, and the next step. */
export function PermitPage() {
  const { projectId, permitId } = useParams();
  const id = Number(permitId);
  const { api, can, districtId } = useSession();
  const loaded = useLoad(() => api.getPermit(id), [api, id, districtId]);
  const registry = useLoad(() => api.permitRegistry(), [api]);
  const [permit, setPermit] = useState<PermitApplication | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [note, setNote] = useState<string | null>(null);
  useEffect(() => setPermit(loaded.data), [loaded.data]);

  const act: Act = async (action, done) => {
    setError(null);
    setNote(null);
    try {
      setPermit(await action());
      if (done) setNote(done);
    } catch (err) {
      setError(err);
    }
  };
  const process = can("permit.process");
  const open = permit !== null && ["received", "review", "reported", "deferred", "granted"].includes(permit.status);

  return (
    <section className="page">
      <p>
        <Link to={`/projects/${projectId}/permits`}>← All applications</Link>
      </p>
      <ErrorMessage error={error ?? loaded.error ?? registry.error} />
      {note && <p role="status">{note}</p>}
      {permit && registry.data && (
        <>
          <h1>
            {permit.number} <span className="muted small">· {permit.status_label}</span>
          </h1>
          <dl className="facts">
            <dt>Applicant</dt>
            <dd>
              {permit.applicant_name}
              {permit.applicant_phone !== "restricted" && (permit.applicant_phone || permit.applicant_email) && (
                <span className="muted small"> · {[permit.applicant_phone, permit.applicant_email, permit.applicant_address].filter(Boolean).join(" · ")}</span>
              )}
            </dd>
            <dt>For</dt>
            <dd>
              {permit.kind === "development" ? "Development permit" : "Planning permit"}: {permit.category_label}
            </dd>
            <dt>Proposed use</dt>
            <dd>
              {permit.proposed_use || "—"}
              {permit.proposed_floors !== null && `, ${permit.proposed_floors} storey(s)`}
            </dd>
            <dt>Received</dt>
            <dd>{permit.received_on}</dd>
            <dt>Officer</dt>
            <dd>
              <OfficerPicker key={permit.id} kind="permit" id={permit.id} officer={permit.officer} />
            </dd>
            <dt>Site</dt>
            <dd>
              {permit.site ? <Link to={`/projects/${projectId}`}>On the project's map, in the permits layer</Link> : "Not on the map yet"}
              {permit.site && permit.checks?.zone?.value && (
                <>
                  {" · "}
                  <button type="button" className="link" onClick={async () => saveBlob(await api.permitPaper(permit.id, "land-use-certificate"), `land-use-${permit.number.replace(/\//g, "-")}.pdf`)}>
                    Land Use Certificate
                  </button>
                </>
              )}
            </dd>
          </dl>

          <NextStep permit={permit} registry={registry.data} act={act} />
          {["granted", "issued", "refused"].includes(permit.status) && <Challenges permit={permit} act={act} />}

          <Card title="Deadlines">
            <ul>
              {permit.clocks.map((clock) => (
                <li key={clock.code} className={clock.overdue || clock.late ? "error" : undefined}>
                  {clock.label}: {clockState(clock)} <span className="muted small">({clock.rule}, {clock.days} days)</span>
                </li>
              ))}
            </ul>
          </Card>

          <Card title="Automatic checks">
            <p className="muted small">
              Made from the map against the zone's standard (r.44(7)(a)). They are advice to the Technical Sub-Committee and the Spatial
              Planning Committee, not the decision.
            </p>
            {permit.checks ? (
              <table className="data">
                <tbody>
                  {permit.checks.results.map((check) => (
                    <tr key={check.code}>
                      <th scope="row">{check.label}</th>
                      <td className={check.outcome === "fail" ? "error" : undefined}>{OUTCOME[check.outcome]}</td>
                      <td>{check.detail}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p>Not run yet.</p>
            )}
            {process && open && (
              <button type="button" className="secondary" onClick={() => void act(() => api.checkPermit(permit.id), "Checks run again.")}>
                Run the checks again
              </button>
            )}
          </Card>

          <Documents permit={permit} registry={registry.data} act={act} canEdit={process && open} />
          <Comments permit={permit} act={act} canEdit={process && open} />

          {permit.inspections.length > 0 && (
            <Card title="Site inspections">
              {permit.inspections.map((inspection) => (
                <div key={inspection.id}>
                  <h3>
                    {inspection.inspected_on} <span className="muted small">{inspection.inspected_by}</span>
                  </h3>
                  <dl className="facts">
                    {registry.data!.inspection_points
                      .filter((point) => inspection.findings[point.code])
                      .map((point) => (
                        <div key={point.code} style={{ display: "contents" }}>
                          <dt>{point.label}</dt>
                          <dd>{inspection.findings[point.code]}</dd>
                        </div>
                      ))}
                  </dl>
                  {inspection.summary && <p>{inspection.summary}</p>}
                </div>
              ))}
            </Card>
          )}

          <Card title="History">
            <ul>
              {permit.events.map((event, i) => (
                <li key={i}>
                  {event.on}: {EVENTS[event.kind] ?? event.kind}
                  {event.note && `: ${event.note}`} <span className="muted small">{event.by}</span>
                </li>
              ))}
            </ul>
            {process && open && (
              <button
                type="button"
                className="link"
                onClick={() => window.confirm("Withdraw this application? Its deadlines stop.") && void act(() => api.withdrawPermit(permit.id), "Application withdrawn.")}
              >
                Withdraw the application
              </button>
            )}
          </Card>
        </>
      )}
    </section>
  );
}
