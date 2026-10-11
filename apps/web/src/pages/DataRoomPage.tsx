import type { DataRoomSettings, InformationRequest, RoomDocumentKind } from "@spatial/map-core";
import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { ErrorMessage } from "../components/ErrorMessage";
import { useLoad } from "../components/useLoad";
import { useSession } from "../session";

const KINDS: [RoomDocumentKind, string][] = [
  ["notice", "Notice"],
  ["local_plan", "Local plan"],
  ["structure_plan", "Structure plan"],
  ["sdf", "Spatial Development Framework"],
  ["zoning_scheme", "Zoning scheme"],
  ["consultation", "Record of public consultation"],
  ["outsourced", "Scope of outsourced services"],
  ["other", "Other document"],
];

function Settings({ canManage }: { canManage: boolean }) {
  const { api, districtId } = useSession();
  const loaded = useLoad(() => api.getDataRoom(), [api, districtId]);
  const [room, setRoom] = useState<DataRoomSettings | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [note, setNote] = useState<string | null>(null);
  useEffect(() => setRoom(loaded.data), [loaded.data]);

  async function save(changes: Partial<DataRoomSettings>, done: string) {
    setError(null);
    setNote(null);
    try {
      setRoom(await api.updateDataRoom(changes));
      setNote(done);
    } catch (err) {
      setError(err);
    }
  }

  return (
    <section aria-label="Opening" className="card wide">
      <h2>Opening</h2>
      <ErrorMessage error={error ?? loaded.error} />
      {note && <p role="status">{note}</p>}
      {room && (
        <>
          <p>
            The room is <strong>{room.is_open ? "open online" : "closed online"}</strong>.{" "}
            {room.is_open ? (
              <>
                The public page is <Link to={`/public/${room.code}`}>/public/{room.code}</Link>.
              </>
            ) : (
              "Nothing is shown to the public until it is opened."
            )}
          </p>
          {canManage && (
            <form
              className="stack"
              aria-label="Data room settings"
              onSubmit={(e: FormEvent) => {
                e.preventDefault();
                void save({ welcome: room.welcome, contact: room.contact }, "Saved.");
              }}
            >
              <div className="inline-form">
                <button type="button" onClick={() => void save({ is_open: !room.is_open }, room.is_open ? "The room is closed online." : "The room is open online.")}>
                  {room.is_open ? "Close the room online" : "Open the room online"}
                </button>
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={room.show_applicants}
                    onChange={(e) => void save({ show_applicants: e.target.checked }, e.target.checked ? "The register now names applicants." : "The register no longer names applicants.")}
                  />{" "}
                  Name the people permits were issued to in the register
                </label>
              </div>
              <p className="muted small">
                Names are personal data (L.I. 2384 r.68(2)(b)): leave this off unless the Assembly has decided to publish them. Phone
                numbers, emails and addresses are never shown.
              </p>
              <label>
                Welcome (shown at the top of the public page)
                <textarea aria-label="Welcome" rows={2} value={room.welcome} onChange={(e) => setRoom({ ...room, welcome: e.target.value })} />
              </label>
              <label>
                The office: where, hours, phone, email
                <textarea aria-label="The office" rows={3} value={room.contact} onChange={(e) => setRoom({ ...room, contact: e.target.value })} />
              </label>
              <div className="inline-form">
                <button type="submit" className="secondary">
                  Save the text
                </button>
              </div>
            </form>
          )}
        </>
      )}
    </section>
  );
}

function Publications({ canManage }: { canManage: boolean }) {
  const { api, districtId } = useSession();
  const list = useLoad(() => api.listPublications(), [api, districtId]);
  const projects = useLoad(() => api.listProjects(), [api, districtId]);
  const [project, setProject] = useState("");
  const [error, setError] = useState<unknown>(null);
  const published = new Set(list.data?.map((p) => p.project));
  const run = async (action: () => Promise<unknown>) => {
    setError(null);
    await action().catch(setError);
    list.reload();
  };
  return (
    <section aria-label="Published projects" className="card wide">
      <h2>Published projects</h2>
      <p className="muted small">
        A published project's permits appear in the public register, and its zoning answers "What can I build here?". Untick either to
        keep it out.
      </p>
      <ErrorMessage error={error ?? list.error} />
      {list.data?.length === 0 && <p>No project is published.</p>}
      {list.data && list.data.length > 0 && (
        <table className="data">
          <thead>
            <tr>
              <th>Project</th>
              <th>Permits in the register</th>
              <th>Zoning lookup</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {list.data.map((p) => (
              <tr key={p.id}>
                <td>{p.project_name}</td>
                <td>
                  <input type="checkbox" aria-label={`Permits of ${p.project_name}`} disabled={!canManage} checked={p.permits} onChange={(e) => void run(() => api.updatePublication(p.id, { permits: e.target.checked }))} />
                </td>
                <td>
                  <input type="checkbox" aria-label={`Zoning of ${p.project_name}`} disabled={!canManage} checked={p.zoning} onChange={(e) => void run(() => api.updatePublication(p.id, { zoning: e.target.checked }))} />
                </td>
                <td>
                  {canManage && (
                    <button type="button" className="link" aria-label={`Stop publishing ${p.project_name}`} onClick={() => void run(() => api.unpublishProject(p.id))}>
                      Stop publishing
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {canManage && (
        <form
          className="inline-form"
          aria-label="Publish a project"
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            if (project) void run(() => api.publishProject(Number(project))).then(() => setProject(""));
          }}
        >
          <label>
            Project
            <select aria-label="Project to publish" value={project} onChange={(e) => setProject(e.target.value)}>
              <option value="">Choose…</option>
              {projects.data?.results
                .filter((p) => !published.has(p.id))
                .map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
            </select>
          </label>
          <button type="submit" disabled={!project}>
            Publish
          </button>
        </form>
      )}
    </section>
  );
}

function Documents({ canManage }: { canManage: boolean }) {
  const { api, districtId } = useSession();
  const list = useLoad(() => api.listRoomDocuments(), [api, districtId]);
  const [file, setFile] = useState<File | null>(null);
  const [kind, setKind] = useState<RoomDocumentKind>("notice");
  const [title, setTitle] = useState("");
  const [until, setUntil] = useState("");
  const [error, setError] = useState<unknown>(null);
  const today = new Date().toISOString().slice(0, 10);
  return (
    <section aria-label="Documents on display" className="card wide">
      <h2>Documents on display</h2>
      <p className="muted small">
        Plans, notices and records of consultation (L.I. 2384 r.64(2)). A draft local plan is on display for 60 days (r.23): give the
        last day and it comes down by itself.
      </p>
      <ErrorMessage error={error ?? list.error} />
      {list.data?.length === 0 && <p>Nothing has been put on display.</p>}
      <ul>
        {list.data?.map((doc) => {
          const state = doc.display_from > today ? `from ${doc.display_from}` : doc.display_until && doc.display_until < today ? `came down on ${doc.display_until}` : doc.display_until ? `on display until ${doc.display_until}` : "on display";
          return (
            <li key={doc.id}>
              <strong>{doc.title}</strong> <span className="muted small">{doc.kind_label}, {state}</span>{" "}
              {canManage && (
                <button
                  type="button"
                  className="link"
                  aria-label={`Remove ${doc.title}`}
                  onClick={async () => {
                    await api.deleteRoomDocument(doc.id).catch(setError);
                    list.reload();
                  }}
                >
                  Remove
                </button>
              )}
            </li>
          );
        })}
      </ul>
      {canManage && (
        <form
          className="inline-form"
          aria-label="Put a document on display"
          onSubmit={async (e: FormEvent) => {
            e.preventDefault();
            if (!file) return;
            setError(null);
            try {
              await api.uploadRoomDocument({ file, kind, title, display_until: until });
              setTitle("");
              setUntil("");
              setFile(null);
              (e.target as HTMLFormElement).reset();
              list.reload();
            } catch (err) {
              setError(err);
            }
          }}
        >
          <label>
            File
            <input type="file" aria-label="Document to display" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </label>
          <label>
            It is a
            <select aria-label="Kind of document" value={kind} onChange={(e) => setKind(e.target.value as RoomDocumentKind)}>
              {KINDS.map(([code, label]) => (
                <option key={code} value={code}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Title
            <input required aria-label="Title" value={title} onChange={(e) => setTitle(e.target.value)} />
          </label>
          <label>
            On display until (optional)
            <input type="date" aria-label="On display until" value={until} onChange={(e) => setUntil(e.target.value)} />
          </label>
          <button type="submit" disabled={!file}>
            Put on display
          </button>
        </form>
      )}
    </section>
  );
}

function Requests() {
  const { api, districtId } = useSession();
  const list = useLoad(() => api.listInformationRequests(), [api, districtId]);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [error, setError] = useState<unknown>(null);
  const answer = async (item: InformationRequest, declined: boolean) => {
    setError(null);
    await api.answerInformationRequest(item.id, answers[item.id] ?? "", declined).catch(setError);
    list.reload();
  };
  return (
    <section aria-label="Requests for information" className="card wide">
      <h2>Requests for information</h2>
      <p className="muted small">
        Each is due an answer within {list.data?.answer_within_days ?? 5} days of being received, and all are kept on record (L.I. 2384
        r.64(7)–(8)).
      </p>
      <ErrorMessage error={error ?? list.error} />
      {list.data && (
        <p>
          {list.data.open} open{list.data.overdue > 0 && <span className="error">, {list.data.overdue} past their five days</span>}.
        </p>
      )}
      {list.data?.results.map((item) => (
        <article key={item.id} aria-label={item.reference} className="stack">
          <h3>
            {item.reference}: {item.subject}{" "}
            <span className={item.overdue || item.late ? "error small" : "muted small"}>
              {item.status === "open" ? (item.overdue ? `overdue since ${item.due_on}` : `due by ${item.due_on}`) : `${item.status} on ${item.answered_on}${item.late ? ", late" : ""}`}
            </span>
          </h3>
          <p className="muted small">
            {item.name} · {[item.phone, item.email].filter(Boolean).join(" · ")} · received {item.received_on}
          </p>
          <p>{item.body}</p>
          {item.status === "open" ? (
            <div className="stack">
              <label>
                The answer given
                <textarea aria-label={`Answer to ${item.reference}`} rows={2} value={answers[item.id] ?? ""} onChange={(e) => setAnswers({ ...answers, [item.id]: e.target.value })} />
              </label>
              <div className="inline-form">
                <button type="button" disabled={!answers[item.id]} onClick={() => void answer(item, false)}>
                  Record the answer
                </button>
                <button type="button" className="secondary" disabled={!answers[item.id]} onClick={() => void answer(item, true)}>
                  Decline, with this reason
                </button>
              </div>
            </div>
          ) : (
            <p>
              <strong>{item.status === "declined" ? "Declined" : "Answer"}:</strong> {item.answer} <span className="muted small">{item.answered_by}</span>
            </p>
          )}
        </article>
      ))}
    </section>
  );
}

/** The district's Public Data Room: what is shown to the public, and their requests. */
export function DataRoomPage() {
  const { can } = useSession();
  const canManage = can("dataroom.manage");
  return (
    <section className="page">
      <h1>Public Data Room</h1>
      <p className="muted">
        What the Assembly puts before the public (Act 925 s.47; L.I. 2384 r.64, r.67): the register of permits, plans and notices, a
        zoning lookup, and requests for information.
      </p>
      <Settings canManage={canManage} />
      <Publications canManage={canManage} />
      <Documents canManage={canManage} />
      {can("dataroom.answer") && <Requests />}
    </section>
  );
}
