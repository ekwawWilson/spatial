import type { AgendaItem, CommitteeKind, CommitteeMember, Committees, Meeting } from "@spatial/map-core";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ErrorMessage } from "../components/ErrorMessage";
import { useLoad } from "../components/useLoad";
import { saveBlob } from "../components/workspace/ExportDialog";
import { useSession } from "../session";

function Members({ data, onSaved }: { data: Committees; onSaved(next: Committees): void }) {
  const { api, can } = useSession();
  const [editing, setEditing] = useState<CommitteeKind | null>(null);
  const [rows, setRows] = useState<CommitteeMember[]>([]);
  const [error, setError] = useState<unknown>(null);
  const label = (code: string) => data.offices.find((o) => o.code === code)?.label ?? code;

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!editing) return;
    setError(null);
    try {
      onSaved(await api.setCommitteeMembers(editing, rows.filter((r) => r.name.trim())));
      setEditing(null);
    } catch (err) {
      setError(err);
    }
  }

  return (
    <section aria-label="Members" className="card wide">
      <h2>Members</h2>
      <p className="muted small">
        Who sits on each committee, and in which office: the quorum of r.7 needs particular offices present (the DCE or Coordinating Director,
        Physical Planning, Development Planning, Works, Lands Commission, EPA, Roads; and Disaster Prevention for the Spatial Planning Committee).
      </p>
      <ErrorMessage error={error} />
      {data.committees.map((committee) =>
        editing === committee.kind ? (
          <form key={committee.kind} className="stack" aria-label={`Members of the ${committee.label}`} onSubmit={save}>
            <h3>{committee.label}</h3>
            {rows.map((row, i) => (
              <div key={i} className="inline-form">
                <input aria-label={`Member ${i + 1}`} placeholder="Name" value={row.name} onChange={(e) => setRows(rows.map((r, j) => (j === i ? { ...r, name: e.target.value } : r)))} />
                <select aria-label={`Office of member ${i + 1}`} value={row.office} onChange={(e) => setRows(rows.map((r, j) => (j === i ? { ...r, office: e.target.value } : r)))}>
                  {data.offices.map((o) => (
                    <option key={o.code} value={o.code}>
                      {o.label}
                    </option>
                  ))}
                </select>
                <button type="button" className="link danger" onClick={() => setRows(rows.filter((_, j) => j !== i))}>
                  Remove
                </button>
              </div>
            ))}
            <div className="inline-form">
              <button type="button" className="secondary" onClick={() => setRows([...rows, { name: "", office: "other" }])}>
                Add a member
              </button>
              <button type="submit">Save the members</button>
              <button type="button" className="link" onClick={() => setEditing(null)}>
                Cancel
              </button>
            </div>
          </form>
        ) : (
          <article key={committee.kind} className="stack">
            <h3>
              {committee.label} <span className="muted small">· {committee.members.length} members</span>
            </h3>
            {committee.members.length > 0 ? (
              <p className="small">{committee.members.map((m) => `${m.name} (${label(m.office)})`).join("; ")}</p>
            ) : (
              <p className="muted small">No members recorded yet.</p>
            )}
            {can("permit.decide") && (
              <div className="inline-form">
                <button type="button" className="secondary" onClick={() => (setRows(committee.members.length ? committee.members : [{ name: "", office: "physical_planning" }]), setEditing(committee.kind))}>
                  Edit the members
                </button>
              </div>
            )}
          </article>
        ),
      )}
    </section>
  );
}

/** The district's two planning committees: their members and their meetings. */
export function CommitteesPage() {
  const { api, can, districtId } = useSession();
  const navigate = useNavigate();
  const committees = useLoad(() => api.listCommittees(), [api, districtId]);
  const meetings = useLoad(() => api.listMeetings(), [api, districtId]);
  const [data, setData] = useState<Committees | null>(null);
  const [values, setValues] = useState({ committee: "tsc" as CommitteeKind, held_on: "", venue: "" });
  const [error, setError] = useState<unknown>(null);
  useEffect(() => setData(committees.data), [committees.data]);

  async function create(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const made = await api.createMeeting(values);
      navigate(`/committees/${made.id}`);
    } catch (err) {
      setError(err);
    }
  }

  return (
    <section className="page">
      <h1>Committees</h1>
      <p className="muted">
        The District Spatial Planning Committee and its Technical Sub-Committee: their meetings, built from the applications and plans waiting
        for them, with the notice, attendance, quorum and minutes the Regulations require (L.I. 2384 r.6–7).
      </p>
      <ErrorMessage error={error ?? committees.error ?? meetings.error} />
      {can("permit.process") && (
        <form className="inline-form card wide" aria-label="New meeting" onSubmit={create}>
          <label>
            Committee
            <select aria-label="Committee" value={values.committee} onChange={(e) => setValues({ ...values, committee: e.target.value as CommitteeKind })}>
              <option value="tsc">Technical Sub-Committee</option>
              <option value="dspc">District Spatial Planning Committee</option>
            </select>
          </label>
          <label>
            Date
            <input required type="date" aria-label="Date" value={values.held_on} onChange={(e) => setValues({ ...values, held_on: e.target.value })} />
          </label>
          <label>
            Venue
            <input aria-label="Venue" value={values.venue} onChange={(e) => setValues({ ...values, venue: e.target.value })} />
          </label>
          <button type="submit">Plan the meeting</button>
        </form>
      )}
      {meetings.data && meetings.data.results.length > 0 && (
        <table className="data" aria-label="Meetings">
          <thead>
            <tr>
              <th>Meeting</th>
              <th>Agenda</th>
              <th>Notice</th>
              <th>Quorum</th>
            </tr>
          </thead>
          <tbody>
            {meetings.data.results.map((m) => (
              <tr key={m.id}>
                <td>
                  <Link to={`/committees/${m.id}`}>
                    {m.committee_label}, {m.held_on}
                  </Link>
                  <div className="muted small">{m.venue}</div>
                </td>
                <td>
                  {m.considered} of {m.items} considered
                </td>
                <td className={m.notice.overdue || m.notice.late ? "error" : undefined}>
                  {m.notice.served_on ? `Served ${m.notice.served_on}` : `Serve by ${m.notice.serve_by}`}
                </td>
                <td>
                  <span className={`pill ${m.quorum.met ? "ok" : "warn"}`}>{m.quorum.met ? "Formed" : `${m.quorum.present} of ${m.quorum.needed}`}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {meetings.data?.results.length === 0 && <p className="muted">No meetings yet.</p>}
      {data && <Members data={data} onSaved={setData} />}
    </section>
  );
}

/** One meeting: its agenda and minutes, who attended, the quorum, and the papers. */
export function MeetingPage() {
  const { meetingId } = useParams();
  const id = Number(meetingId);
  const { api, can, districtId } = useSession();
  const loaded = useLoad(() => api.getMeeting(id), [api, id, districtId]);
  const committees = useLoad(() => api.listCommittees(), [api, districtId]);
  const [meeting, setMeeting] = useState<Meeting | null>(null);
  const [agenda, setAgenda] = useState<AgendaItem[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [note, setNote] = useState<string | null>(null);
  useEffect(() => {
    if (!loaded.data) return;
    setMeeting(loaded.data);
    setAgenda(loaded.data.agenda);
  }, [loaded.data]);
  const canEdit = can("permit.process");

  const save = async (data: Parameters<typeof api.updateMeeting>[1], done: string) => {
    setError(null);
    setNote(null);
    try {
      const next = await api.updateMeeting(id, data);
      setMeeting(next);
      setAgenda(next.agenda);
      setNote(done);
    } catch (err) {
      setError(err);
    }
  };

  const outcomes = committees.data?.outcomes ?? [];
  const link = (item: AgendaItem) =>
    item.project === null
      ? null
      : item.type === "permit"
        ? `/projects/${item.project}/permits/${item.ref}`
        : item.type === "land"
          ? `/projects/${item.project}/land/${item.ref}`
          : item.type === "plan"
            ? `/projects/${item.project}/plan`
            : item.type === "street"
              ? `/projects/${item.project}/addressing`
              : null;

  return (
    <section className="page">
      <p>
        <Link to="/committees">← Committees</Link>
      </p>
      <ErrorMessage error={error ?? loaded.error} />
      {note && <p role="status">{note}</p>}
      {meeting && (
        <>
          <h1>
            {meeting.committee_label} <span className="muted small">· {meeting.held_on}</span>
          </h1>
          <dl className="facts" aria-label="Meeting">
            <dt>Venue</dt>
            <dd>{meeting.venue || "—"}</dd>
            <dt>Notice (Form 5)</dt>
            <dd className={meeting.notice.overdue || meeting.notice.late ? "error" : undefined}>
              {meeting.notice.served_on ? `Served ${meeting.notice.served_on}${meeting.notice.late ? ", late" : ""}` : `To be served by ${meeting.notice.serve_by}`}{" "}
              <span className="muted small">(at least 3 days before, {meeting.notice.rule})</span>
            </dd>
            <dt>Quorum</dt>
            <dd className={meeting.quorum.met ? undefined : "error"}>
              {meeting.quorum.met ? "Formed" : "Not formed"}: {meeting.quorum.present} present, {meeting.quorum.needed} needed ({meeting.quorum.rule})
              {meeting.quorum.missing_offices.length > 0 && <div className="small">Absent: {meeting.quorum.missing_offices.join("; ")}</div>}
            </dd>
          </dl>
          <div className="inline-form">
            {canEdit && !meeting.notice.served_on && (
              <button type="button" className="secondary" onClick={() => void save({ notice_served_on: new Date().toISOString().slice(0, 10) }, "Notice recorded as served today.")}>
                Notice served today
              </button>
            )}
            <button type="button" className="secondary" onClick={async () => saveBlob(await api.meetingPaper(id, "notice"), `notice-${meeting.held_on}.pdf`)}>
              Download the notice (Form 5)
            </button>
            <button type="button" className="secondary" onClick={async () => saveBlob(await api.meetingPaper(id, "minutes"), `minutes-${meeting.held_on}.pdf`)}>
              Download the minutes
            </button>
          </div>

          <section aria-label="Attendance" className="card wide">
            <h2>Attendance</h2>
            {meeting.members.length === 0 && (
              <p className="muted">
                No members recorded for this committee: add them on the <Link to="/committees">Committees</Link> page.
              </p>
            )}
            <div className="stack">
              {meeting.members.map((m) => (
                <label key={m.name} className="checkbox">
                  <input
                    type="checkbox"
                    disabled={!canEdit}
                    checked={meeting.attendance.includes(m.name)}
                    onChange={(e) =>
                      void save(
                        { attendance: e.target.checked ? [...meeting.attendance, m.name] : meeting.attendance.filter((n) => n !== m.name) },
                        "Attendance saved.",
                      )
                    }
                  />
                  {m.name} <span className="muted small">{committees.data?.offices.find((o) => o.code === m.office)?.label}</span>
                </label>
              ))}
            </div>
          </section>

          <form
            className="card wide stack"
            aria-label="Agenda and minutes"
            onSubmit={(e: FormEvent) => {
              e.preventDefault();
              void save({ agenda }, "Minutes saved.");
            }}
          >
            <h2>Agenda and minutes</h2>
            {agenda.length === 0 && <p className="muted">Nothing is waiting for this committee.</p>}
            {agenda.map((item, i) => {
              const to = link(item);
              return (
                <article key={`${item.type}-${item.ref ?? i}`} className="stack">
                  <h3>
                    {i + 1}. {to ? <Link to={to}>{item.title}</Link> : item.title}
                  </h3>
                  <div className="inline-form">
                    <label>
                      Outcome
                      <select aria-label={`Outcome of item ${i + 1}`} disabled={!canEdit} value={item.outcome} onChange={(e) => setAgenda(agenda.map((a, j) => (j === i ? { ...a, outcome: e.target.value } : a)))}>
                        {outcomes.map((o) => (
                          <option key={o.code} value={o.code}>
                            {o.label}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>
                  <label>
                    Minute
                    <textarea aria-label={`Minute of item ${i + 1}`} rows={2} disabled={!canEdit} value={item.minute} onChange={(e) => setAgenda(agenda.map((a, j) => (j === i ? { ...a, minute: e.target.value } : a)))} />
                  </label>
                </article>
              );
            })}
            {canEdit && (
              <div className="inline-form">
                <button type="submit">Save the minutes</button>
                <button type="button" className="secondary" onClick={() => setAgenda([...agenda, { type: "other", ref: null, project: null, title: "Any other business", outcome: "", minute: "" }])}>
                  Add an item
                </button>
                <button
                  type="button"
                  className="secondary"
                  onClick={async () => {
                    setError(null);
                    try {
                      const next = await api.refreshAgenda(id);
                      setMeeting(next);
                      setAgenda(next.agenda);
                      setNote(`${next.added} new item(s) added to the agenda.`);
                    } catch (err) {
                      setError(err);
                    }
                  }}
                >
                  Add what has come in since
                </button>
              </div>
            )}
          </form>
        </>
      )}
    </section>
  );
}
