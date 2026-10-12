import type { PublicPlan, PublicRoom, PublicStatus, PublicZone, RegisterEntry } from "@spatial/map-core";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { ErrorMessage } from "../components/ErrorMessage";
import { useLoad } from "../components/useLoad";
import { useSession } from "../session";

function size(bytes: number): string {
  return bytes >= 1024 ** 2 ? `${(bytes / 1024 ** 2).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

/** The Assemblies whose data room is open online. */
export function PublicRoomsPage() {
  const { api } = useSession();
  const rooms = useLoad(() => api.publicRooms(), [api]);
  return (
    <main className="page">
      <h1>Public Data Rooms</h1>
      <p className="muted">Plans, permits and notices the Assemblies put before the public, under the Land Use and Spatial Planning Act, 2016.</p>
      <ErrorMessage error={rooms.error} />
      {rooms.data?.length === 0 && <p>No Assembly has opened its data room online yet.</p>}
      <ul>
        {rooms.data?.map((room) => (
          <li key={room.code}>
            <Link to={`/public/${room.code}`}>{room.assembly}</Link>
          </li>
        ))}
      </ul>
    </main>
  );
}

function standardLines(zone: Extract<PublicZone, { found: true }>): string[] {
  const s = zone.standard;
  if (!s) return [];
  const lines: string[] = [];
  if (s.min_plot_m2 !== null) lines.push(`Plot of at least ${s.min_plot_m2.toLocaleString("en-GB")} m²`);
  if (s.min_width_m !== null) lines.push(`At least ${s.min_width_m} m wide at the street`);
  if (s.max_coverage_pct !== null) lines.push(`Building on up to ${s.max_coverage_pct}% of the plot`);
  if (s.min_floors !== null && s.max_floors !== null) lines.push(`${s.min_floors} to ${s.max_floors} storeys`);
  else if (s.max_floors !== null) lines.push(`Up to ${s.max_floors} storeys`);
  else if (s.min_floors !== null) lines.push(`At least ${s.min_floors} storeys`);
  const sides = [s.front_setback_m, s.side_setback_m, s.rear_setback_m];
  if (sides.some((v) => v !== null)) lines.push(`Kept back from the boundary: ${sides[0] ?? "—"} m at the front, ${sides[1] ?? "—"} m at the sides, ${sides[2] ?? "—"} m at the back`);
  else if (s.min_setback_m !== null) lines.push(`Kept ${s.min_setback_m} m back from every boundary`);
  return lines;
}

function WhatCanIBuild({ code }: { code: string }) {
  const { api } = useSession();
  const [lat, setLat] = useState("");
  const [lon, setLon] = useState("");
  const [zone, setZone] = useState<PublicZone | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function look(latitude: number, longitude: number) {
    setError(null);
    setZone(null);
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return setError(new Error("Give the latitude and the longitude as numbers, e.g. 5.6037 and -0.1870."));
    setBusy(true);
    try {
      setZone(await api.publicZone(code, longitude, latitude));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  function here() {
    setError(null);
    if (!("geolocation" in navigator)) return setError(new Error("This device can't tell where it is. Type the coordinates instead."));
    setBusy(true);
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLat(position.coords.latitude.toFixed(6));
        setLon(position.coords.longitude.toFixed(6));
        void look(position.coords.latitude, position.coords.longitude);
      },
      () => {
        setBusy(false);
        setError(new Error("Your location couldn't be found. Allow location for this site, or type the coordinates."));
      },
      { enableHighAccuracy: true, timeout: 20_000 },
    );
  }

  return (
    <section aria-label="What can I build here?" className="card wide">
      <h2>What can I build here?</h2>
      <p className="muted small">Stand on the plot and use your location, or type its coordinates (from a site plan or a maps app).</p>
      <form
        className="inline-form"
        aria-label="Find the zone"
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          void look(Number(lat), Number(lon));
        }}
      >
        <button type="button" className="secondary" disabled={busy} onClick={here}>
          Use my location
        </button>
        <label>
          Latitude
          <input aria-label="Latitude" inputMode="decimal" value={lat} onChange={(e) => setLat(e.target.value)} placeholder="5.6037" />
        </label>
        <label>
          Longitude
          <input aria-label="Longitude" inputMode="decimal" value={lon} onChange={(e) => setLon(e.target.value)} placeholder="-0.1870" />
        </label>
        <button type="submit" disabled={busy || !lat || !lon}>
          Find the zone
        </button>
      </form>
      <ErrorMessage error={error} />
      {zone && !zone.found && <p role="status">{zone.detail}</p>}
      {zone?.found && (
        <div role="status">
          <h3>
            {zone.colour && <span aria-hidden="true" style={{ display: "inline-block", width: "1rem", height: "1rem", background: zone.colour, border: "1px solid #555", marginRight: "0.4rem" }} />}
            {zone.code ? `${zone.code}: ` : ""}
            {zone.name}
          </h3>
          <p className="muted small">
            {zone.locality}, from {zone.from}.
          </p>
          {standardLines(zone).length > 0 && (
            <>
              <h4>What the Assembly asks for in this zone</h4>
              <ul>
                {standardLines(zone).map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </>
          )}
          {zone.permitted.length > 0 && (
            <>
              <h4>Uses that may be permitted</h4>
              <ul>
                {zone.permitted.map((use) => (
                  <li key={use}>{use}</li>
                ))}
              </ul>
              <h4>Uses that are prohibited</h4>
              <ul>
                {zone.prohibited.map((use) => (
                  <li key={use}>{use}</li>
                ))}
              </ul>
            </>
          )}
          <p>{zone.note}</p>
        </div>
      )}
    </section>
  );
}

function CheckApplication({ code }: { code: string }) {
  const { api } = useSession();
  const [number, setNumber] = useState("");
  const [result, setResult] = useState<PublicStatus | "none" | null>(null);
  const [error, setError] = useState<unknown>(null);
  return (
    <section aria-label="Check an application" className="card wide">
      <h2>Check an application</h2>
      <form
        className="inline-form"
        aria-label="Application status"
        onSubmit={async (e: FormEvent) => {
          e.preventDefault();
          setError(null);
          setResult(null);
          try {
            setResult((await api.publicStatus(code, number.trim())) ?? "none");
          } catch (err) {
            setError(err);
          }
        }}
      >
        <label>
          Application number (on your acknowledgement)
          <input required aria-label="Application number" value={number} onChange={(e) => setNumber(e.target.value)} placeholder="e.g. SMA/DP/2026/0014" />
        </label>
        <button type="submit">Check</button>
      </form>
      <ErrorMessage error={error} />
      {result === "none" && <p role="status">No application with that number. Check it against your acknowledgement.</p>}
      {result && result !== "none" && (
        <dl className="facts" role="status">
          <dt>{result.number}</dt>
          <dd>
            {result.permit}: <strong>{result.status}</strong>
          </dd>
          <dt>Received</dt>
          <dd>{result.received_on}</dd>
          {result.next_step && (
            <>
              <dt>Next</dt>
              <dd>
                {result.next_step.label}, by {result.next_step.due_on}
              </dd>
            </>
          )}
          {result.issued_on && (
            <>
              <dt>Issued</dt>
              <dd>{result.issued_on}</dd>
            </>
          )}
        </dl>
      )}
    </section>
  );
}

function Register({ code }: { code: string }) {
  const { api } = useSession();
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const register = useLoad(() => api.publicRegister(code, { q: q || undefined, status: status || undefined }), [api, code, q, status]);
  const rows: RegisterEntry[] = register.data?.results ?? [];
  const names = rows.some((r) => r.applicant !== null);
  return (
    <section aria-label="Register of permits" className="card wide">
      <h2>Register of permits</h2>
      <p className="muted small">Permits issued, applications being considered, and applications refused with the grounds (L.I. 2384 r.67).</p>
      <div className="inline-form">
        <label>
          Find
          <input aria-label="Find in the register" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Number or locality" />
        </label>
        <label>
          Show
          <select aria-label="Show" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">Everything</option>
            <option value="issued">Permits issued</option>
            <option value="granted">Granted</option>
            <option value="pending">Pending</option>
            <option value="deferred">Deferred</option>
            <option value="refused">Refused</option>
          </select>
        </label>
      </div>
      <ErrorMessage error={register.error} />
      {register.data && rows.length === 0 && <p>Nothing in the register {q || status ? "matches" : "yet"}.</p>}
      {rows.length > 0 && (
        <table className="data">
          <thead>
            <tr>
              <th>Number</th>
              <th>Permit</th>
              <th>Locality</th>
              {names && <th>Issued to</th>}
              <th>Status</th>
              <th>Dates</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.number}>
                <td>{row.number}</td>
                <td>
                  {row.for}
                  {row.proposed_use && <div className="muted small">{row.proposed_use}</div>}
                </td>
                <td>{row.locality}</td>
                {names && <td>{row.applicant}</td>}
                <td>
                  {row.status}
                  {row.expired && <span className="error"> (expired)</span>}
                  {row.reasons && <div className="small">Grounds: {row.reasons}</div>}
                </td>
                <td className="small">
                  Received {row.received_on}
                  {row.issued_on && `; issued ${row.issued_on}; valid until ${row.expires_on}`}
                  {!row.issued_on && row.decided_on && `; decided ${row.decided_on}`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function PlanCommentForm({ code, plan, topics }: { code: string; plan: PublicPlan; topics: { code: string; label: string }[] }) {
  const { api } = useSession();
  const [values, setValues] = useState({ name: "", contact: "", topic: "", text: "" });
  const [done, setDone] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const set = (key: keyof typeof values, value: string) => setValues((v) => ({ ...v, [key]: value }));
  if (done) return <p role="status">Thank you. Your comment on {plan.name} has been received and will be put before the Spatial Planning Committee.</p>;
  return (
    <form
      className="stack"
      aria-label={`Comment on ${plan.name}`}
      onSubmit={async (e: FormEvent) => {
        e.preventDefault();
        setError(null);
        try {
          await api.sendPlanComment(code, plan.project, { name: values.name, text: values.text, contact: values.contact || undefined, topic: values.topic || undefined });
          setDone(true);
        } catch (err) {
          setError(err);
        }
      }}
    >
      <ErrorMessage error={error} />
      <div className="inline-form">
        <label>
          Your name
          <input required aria-label={`Your name, for ${plan.name}`} value={values.name} onChange={(e) => set("name", e.target.value)} />
        </label>
        <label>
          Phone or address (optional)
          <input aria-label={`Phone or address, for ${plan.name}`} value={values.contact} onChange={(e) => set("contact", e.target.value)} />
        </label>
        <label>
          About
          <select aria-label={`About, for ${plan.name}`} value={values.topic} onChange={(e) => set("topic", e.target.value)}>
            <option value="">The plan as a whole</option>
            {topics.map((t) => (
              <option key={t.code} value={t.code}>
                {t.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <label>
        Your comment
        <textarea required aria-label={`Your comment on ${plan.name}`} rows={3} maxLength={5000} value={values.text} onChange={(e) => set("text", e.target.value)} />
      </label>
      <div className="inline-form">
        <button type="submit">Send the comment</button>
      </div>
    </form>
  );
}

function Plans({ code }: { code: string }) {
  const { api } = useSession();
  const plans = useLoad(() => api.publicPlans(code), [api, code]);
  if (!plans.data || plans.data.results.length === 0) return null;
  return (
    <section aria-label="Local plans being made" className="card wide">
      <h2>Local plans being made</h2>
      {plans.data.results.map((plan) => (
        <article key={plan.project} className="stack" aria-label={plan.name}>
          <h3>
            {plan.name} <span className="muted small">· {plan.locality}</span>
          </h3>
          <p>
            {plan.approved_on
              ? `Approved on ${plan.approved_on}.`
              : plan.comments_open
                ? `The draft is open for inspection and comment until ${plan.comments_close_on}.`
                : plan.draft_on_display_from
                  ? `The draft was open for comment until ${plan.comments_close_on}.`
                  : `Preparation commenced on ${plan.commenced_on}. The draft is not out yet.`}
          </p>
          {plan.consultations.length > 0 && (
            <>
              <h4>Consultations held</h4>
              <ul>
                {plan.consultations.map((c) => (
                  <li key={`${c.held_on}-${c.venue}`}>
                    <strong>
                      {c.held_on}, {c.venue}
                    </strong>
                    {c.attendance !== null && ` (${c.attendance} attending)`}: {c.issues}
                    {c.outcome && <div className="small">Agreed: {c.outcome}</div>}
                  </li>
                ))}
              </ul>
            </>
          )}
          {plan.comments_open && <PlanCommentForm code={code} plan={plan} topics={plans.data!.topics} />}
        </article>
      ))}
    </section>
  );
}

function LandApplications({ code }: { code: string }) {
  const { api } = useSession();
  const shown = useLoad(() => api.publicLandApplications(code), [api, code]);
  if (!shown.data || shown.data.results.length === 0) return null;
  return (
    <section aria-label="Applications on display" className="card wide">
      <h2>Re-zoning and subdivision applications on display</h2>
      <p className="muted small">
        Anyone may send the Assembly a comment or objection on an application before its closing date (Form 59 of L.I. 2384).
      </p>
      <table className="data">
        <thead>
          <tr>
            <th>Application</th>
            <th>What is asked for</th>
            <th>Locality</th>
            <th>Comments</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {shown.data.results.map((a) => (
            <tr key={a.number}>
              <td>
                {a.number}
                <div className="muted small">{a.kind}</div>
              </td>
              <td>{a.proposal}</td>
              <td>{a.locality}</td>
              <td className="small">{a.comments_close_on ? `until ${a.comments_close_on}` : "—"}</td>
              <td className="small">
                {a.status}
                {a.decided_on && ` on ${a.decided_on}`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function Notices({ code }: { code: string }) {
  const { api } = useSession();
  const notices = useLoad(() => api.publicNotices(code), [api, code]);
  if (!notices.data || notices.data.results.length === 0) return null;
  return (
    <section aria-label="Enforcement notices" className="card wide">
      <h2>Enforcement notices served</h2>
      <table className="data">
        <thead>
          <tr>
            <th>Case</th>
            <th>Notice</th>
            <th>Locality</th>
            <th>Served</th>
          </tr>
        </thead>
        <tbody>
          {notices.data.results.map((n) => (
            <tr key={`${n.case}-${n.notice}-${n.served_on}`}>
              <td>{n.case}</td>
              <td>
                {n.notice}
                <div className="muted small">{n.contravention}</div>
              </td>
              <td>{n.locality}</td>
              <td className="small">
                {n.served_on}
                {n.complied_on ? `; complied with ${n.complied_on}` : n.comply_by ? `; to comply by ${n.comply_by}` : ""}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function Ask({ code, days }: { code: string; days: number }) {
  const { api } = useSession();
  const [values, setValues] = useState({ name: "", phone: "", email: "", subject: "", body: "" });
  const [done, setDone] = useState<{ reference: string; answer_due_on: string } | null>(null);
  const [error, setError] = useState<unknown>(null);
  const set = (key: keyof typeof values, value: string) => setValues((v) => ({ ...v, [key]: value }));
  return (
    <section aria-label="Ask for information" className="card wide">
      <h2>Ask for information</h2>
      <p className="muted small">The Assembly answers requests to its data room within {days} days (L.I. 2384 r.64). It will reach you by the phone number or email you give.</p>
      <ErrorMessage error={error} />
      {done ? (
        <p role="status">
          Received. Your reference is <strong>{done.reference}</strong>; expect an answer by {done.answer_due_on}.
        </p>
      ) : (
        <form
          className="stack"
          aria-label="Request for information"
          onSubmit={async (e: FormEvent) => {
            e.preventDefault();
            setError(null);
            try {
              setDone(await api.askDataRoom(code, { name: values.name, subject: values.subject, body: values.body, phone: values.phone || undefined, email: values.email || undefined }));
            } catch (err) {
              setError(err);
            }
          }}
        >
          <div className="inline-form">
            <label>
              Your name
              <input required aria-label="Your name" value={values.name} onChange={(e) => set("name", e.target.value)} />
            </label>
            <label>
              Phone
              <input aria-label="Phone" value={values.phone} onChange={(e) => set("phone", e.target.value)} />
            </label>
            <label>
              Email
              <input type="email" aria-label="Email" value={values.email} onChange={(e) => set("email", e.target.value)} />
            </label>
          </div>
          <label>
            About
            <input required aria-label="About" value={values.subject} onChange={(e) => set("subject", e.target.value)} placeholder="e.g. The zoning of a plot at Kasoa" />
          </label>
          <label>
            What you would like to know
            <textarea required aria-label="What you would like to know" rows={3} value={values.body} onChange={(e) => set("body", e.target.value)} />
          </label>
          <div className="inline-form">
            <button type="submit">Send the request</button>
          </div>
        </form>
      )}
    </section>
  );
}

/** One Assembly's Public Data Room, for anyone: no sign-in. */
export function PublicRoomPage() {
  const { code = "" } = useParams();
  const { api } = useSession();
  const [room, setRoom] = useState<PublicRoom | "closed" | null>(null);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    setRoom(null);
    api
      .publicRoom(code)
      .then((found) => setRoom(found ?? "closed"))
      .catch(setError);
  }, [api, code]);

  if (room === "closed") {
    return (
      <main className="page">
        <h1>Public Data Room</h1>
        <p role="alert">This Assembly's data room isn't open online. Visit the Physical Planning Department at the Assembly's offices.</p>
        <p>
          <Link to="/public">Other Assemblies</Link>
        </p>
      </main>
    );
  }
  return (
    <main className="page">
      <ErrorMessage error={error} />
      {room && (
        <>
          <h1>{room.assembly}: Public Data Room</h1>
          {room.welcome && <p>{room.welcome}</p>}
          <WhatCanIBuild code={code} />
          <CheckApplication code={code} />
          <Register code={code} />
          <Plans code={code} />
          <LandApplications code={code} />
          <Notices code={code} />
          <section aria-label="Plans and notices" className="card wide">
            <h2>Plans and notices</h2>
            {room.documents.length === 0 && <p>Nothing on display at the moment.</p>}
            <ul>
              {room.documents.map((doc) => (
                <li key={doc.id}>
                  <a href={api.publicDocumentUrl(code, doc.id)}>{doc.title}</a>{" "}
                  <span className="muted small">
                    {doc.kind_label}, {size(doc.size)}
                    {doc.display_until && `, on display until ${doc.display_until}`}
                  </span>
                  {doc.description && <div className="small">{doc.description}</div>}
                </li>
              ))}
            </ul>
            {room.zoning_schemes.length > 0 && (
              <>
                <h3>Zoning schemes</h3>
                <ul>
                  {room.zoning_schemes.map((scheme) => (
                    <li key={scheme.name}>
                      {scheme.name} ({scheme.locality}): {scheme.status.toLowerCase()}
                      {scheme.approved_on && ` on ${scheme.approved_on}`}
                    </li>
                  ))}
                </ul>
              </>
            )}
          </section>
          {room.fees.length > 0 && (
            <section aria-label="Fees" className="card wide">
              <h2>Permit fees</h2>
              <table className="data">
                <tbody>
                  {room.fees.map((fee) => (
                    <tr key={`${fee.stage}-${fee.kind}-${fee.label}`}>
                      <th scope="row">{fee.label}</th>
                      <td>GHS {fee.amount}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}
          <Ask code={code} days={room.answer_within_days} />
          {room.contact && (
            <section aria-label="The office" className="card wide">
              <h2>The office</h2>
              <p style={{ whiteSpace: "pre-line" }}>{room.contact}</p>
            </section>
          )}
        </>
      )}
    </main>
  );
}
