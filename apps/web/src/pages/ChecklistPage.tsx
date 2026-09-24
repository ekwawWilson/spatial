import type {
  BoundaryMetrics,
  Checklist,
  ChecklistItem,
  ChecklistStatus,
  Domain,
  LayerMetrics,
  Member,
} from "@spatial/map-core";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ErrorMessage } from "../components/ErrorMessage";
import { useLoad } from "../components/useLoad";
import { saveBlob } from "../components/workspace/ExportDialog";
import { useSession } from "../session";
import type { ChecklistAction } from "./ProjectWorkspace";

export const STATUS_LABELS: Record<ChecklistStatus, string> = {
  not_started: "Not started",
  in_progress: "In progress",
  ready: "Ready",
  verified: "Verified",
};

const SEND_TO_FIELD_NOTE = "Ground-truthing tasks go to the field app once sync is available (Phase 10).";

function pct(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${Math.round(value)}%`;
}

export function Progress(props: { value: number; label: string }) {
  return (
    <div className="progress" role="progressbar" aria-label={props.label} aria-valuenow={props.value} aria-valuemin={0} aria-valuemax={100}>
      <div style={{ width: `${props.value}%` }} />
    </div>
  );
}

function isLayerMetrics(m: ChecklistItem["metrics"]): m is LayerMetrics {
  return m !== null && "feature_count" in m;
}

function isBoundaryMetrics(m: ChecklistItem["metrics"]): m is BoundaryMetrics {
  return m !== null && "exists" in m;
}

export function ChecklistPage() {
  const { projectId } = useParams();
  const id = Number(projectId);
  const { api, can, districtId } = useSession();
  const load = useLoad(() => api.getChecklist(id), [api, id, districtId]);
  const members = useLoad(
    () => (can("membership.view") ? api.listMembers().then((p) => p.results) : Promise.resolve([] as Member[])),
    [api, districtId],
  );
  const [data, setData] = useState<Checklist | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [open, setOpen] = useState<number | null>(null);

  useEffect(() => {
    if (load.data) setData(load.data);
  }, [load.data]);

  async function run(action: () => Promise<void>) {
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(err);
    }
  }

  async function download(format: "csv" | "pdf") {
    await run(async () => saveBlob(await api.exportChecklist(id, format), `checklist-${id}.${format}`));
  }

  if (load.error) return <ErrorMessage error={load.error} />;
  if (!data) return <p className="page muted">Loading…</p>;

  return (
    <section className="page checklist">
      <p>
        <Link to={`/projects/${id}`}>← {data.project_name}</Link>
      </p>
      <h1>Readiness checklist</h1>
      <div className="inline-form">
        <strong className="score" aria-label="Readiness score">
          {data.score}%
        </strong>
        <span>
          {data.complete} of {data.total} items complete
        </span>
        <span className="spacer" />
        <button type="button" className="secondary" onClick={() => download("csv")}>
          Export CSV
        </button>
        <button type="button" className="secondary" onClick={() => download("pdf")}>
          Export PDF
        </button>
        {can("checklist.edit") && (
          <button
            type="button"
            className="link"
            title="Add items added to the district's template since this project started"
            onClick={() => run(async () => setData(await api.addMissingChecklistItems(id)))}
          >
            Add new template items
          </button>
        )}
      </div>
      <ErrorMessage error={error} />

      <div className="group-progress">
        {data.groups.map((g) => (
          <div key={g.group}>
            <span className="small">
              {g.label} · {g.complete}/{g.total}
            </span>
            <Progress value={(100 * g.complete) / g.total} label={g.label} />
          </div>
        ))}
      </div>

      {data.blockers.length > 0 && (
        <section aria-label="Blockers" className="blockers">
          <h2>Blockers</h2>
          <ul>
            {data.blockers.map((b, i) => (
              <li key={i}>
                <button type="button" className="link" onClick={() => setOpen(b.item)}>
                  {b.title}
                </button>
                : {b.problem}
              </li>
            ))}
          </ul>
        </section>
      )}

      {data.groups.map((g) => (
        <section key={g.group} aria-label={g.label}>
          <h2>{g.label}</h2>
          <table className="data checklist-items">
            <thead>
              <tr>
                <th>Item</th>
                <th>Status</th>
                <th>Measures</th>
                <th>Owner / due</th>
              </tr>
            </thead>
            <tbody>
              {data.items
                .filter((item) => item.group === g.group)
                .map((item) => (
                  <ItemRows
                    key={item.id}
                    projectId={id}
                    item={item}
                    open={open === item.id}
                    members={members.data ?? []}
                    onToggle={() => setOpen(open === item.id ? null : item.id)}
                    onChanged={(next) => {
                      setData((all) => all && { ...all, items: all.items.map((i) => (i.id === next.id ? next : i)) });
                      load.reload(); // the score, progress and blockers follow
                    }}
                    onReload={load.reload}
                    onError={setError}
                  />
                ))}
            </tbody>
          </table>
        </section>
      ))}
    </section>
  );
}

function Measures({ item }: { item: ChecklistItem }) {
  const m = item.metrics;
  if (isLayerMetrics(m)) {
    return (
      <span className="small">
        {m.feature_count} features · coverage {pct(m.coverage)} · attributes {pct(m.attributes)} · verified{" "}
        {pct(m.verified)}
        {m.age_days !== null ? ` · newest ${m.age_days} d old` : ""}
      </span>
    );
  }
  if (isBoundaryMetrics(m)) {
    return (
      <span className="small">
        {m.exists ? `${m.status}, ${m.area_ha?.toFixed(2)} ha${m.overlaps ? `, ${m.overlaps} overlap(s)` : ""}` : "No boundary"}
      </span>
    );
  }
  if (item.kind === "layer") return <span className="small muted">No layer linked</span>;
  return <span className="small muted">{item.attachments.length} document(s)</span>;
}

function ItemRows(props: {
  projectId: number;
  item: ChecklistItem;
  open: boolean;
  members: Member[];
  onToggle(): void;
  onChanged(item: ChecklistItem): void;
  onReload(): void;
  onError(err: unknown): void;
}) {
  const { api, can, me } = useSession();
  const navigate = useNavigate();
  const { item } = props;
  const editable = can("checklist.edit") && (item.status !== "verified" || can("checklist.verify"));
  const [notes, setNotes] = useState(item.notes);
  useEffect(() => setNotes(item.notes), [item.notes]);

  async function save(change: Parameters<typeof api.updateChecklistItem>[1]) {
    try {
      props.onChanged(await api.updateChecklistItem(item.id, change));
    } catch (err) {
      props.onError(err);
    }
  }

  function openWorkspace(action: ChecklistAction) {
    navigate(`/projects/${props.projectId}`, { state: { checklist: action } });
  }

  async function draw() {
    try {
      let layerId = item.linked_layer;
      if (!layerId) layerId = (await api.createChecklistLayer(item.id)).layer;
      openWorkspace({ kind: "draw", layerId });
    } catch (err) {
      props.onError(err);
    }
  }

  const statuses = (Object.keys(STATUS_LABELS) as ChecklistStatus[]).filter(
    (s) => s !== "verified" || can("checklist.verify") || item.status === "verified",
  );

  return (
    <>
      <tr className={item.complete ? "complete" : ""}>
        <td>
          <button type="button" className="link" aria-expanded={props.open} onClick={props.onToggle}>
            {item.complete ? "✓ " : ""}
            {item.title}
          </button>
          {item.blockers.length > 0 && <span className="error small"> ⚠</span>}
        </td>
        <td>
          <select
            aria-label={`Status of ${item.title}`}
            value={item.status}
            disabled={!editable}
            onChange={(e) => save({ status: e.target.value as ChecklistStatus })}
          >
            {statuses.map((s) => (
              <option key={s} value={s}>
                {STATUS_LABELS[s]}
              </option>
            ))}
          </select>
        </td>
        <td>
          <Measures item={item} />
        </td>
        <td className="small">
          {[item.owner_name, item.due_date].filter(Boolean).join(" · ") || "—"}
        </td>
      </tr>
      {props.open && (
        <tr className="details">
          <td colSpan={4}>
            <div role="region" aria-label={`Details of ${item.title}`} className="stack">
              {item.description && <p className="muted">{item.description}</p>}
              {item.checks.length > 0 && (
                <ul className="checks">
                  {item.checks.map((c, i) => (
                    <li key={i} className={c.ok ? "" : "error"}>
                      {c.ok ? "✓" : "✗"} {c.ok ? c.label : c.problem}
                    </li>
                  ))}
                </ul>
              )}
              {item.blockers.map((b, i) => (
                <p key={i} className="error small">
                  {b}
                </p>
              ))}

              <div className="inline-form" role="group" aria-label="Actions">
                {item.kind === "layer" && can("data.import") && (
                  <button
                    type="button"
                    className="secondary"
                    onClick={() =>
                      openWorkspace({
                        kind: "import",
                        binding: {
                          title: item.title,
                          layerId: item.linked_layer,
                          domain: (item.domain || "other") as Domain,
                          geometryType: item.geometry_type || undefined,
                        },
                      })
                    }
                  >
                    Import
                  </button>
                )}
                {item.kind === "layer" && can("data.export") && (
                  <button
                    type="button"
                    className="secondary"
                    disabled={!item.linked_layer}
                    onClick={() => item.linked_layer && openWorkspace({ kind: "export", layerId: item.linked_layer })}
                  >
                    Export
                  </button>
                )}
                {item.kind === "layer" && can("feature.edit") && can("layer.edit") && (
                  <button type="button" className="secondary" onClick={draw}>
                    Draw
                  </button>
                )}
                {item.kind === "layer" && (
                  <button type="button" className="secondary" disabled title={SEND_TO_FIELD_NOTE}>
                    Send to field
                  </button>
                )}
                {item.kind === "boundary" && (
                  <Link to={`/projects/${props.projectId}`}>Open the planning area in the workspace</Link>
                )}
              </div>
              {item.kind === "layer" && <p className="muted small">Send to field: {SEND_TO_FIELD_NOTE}</p>}

              {editable && (
                <div className="inline-form">
                  {props.members.length > 0 ? (
                    <label>
                      Owner
                      <select
                        aria-label="Owner"
                        value={item.owner ?? ""}
                        onChange={(e) => save({ owner: e.target.value ? Number(e.target.value) : null })}
                      >
                        <option value="">Nobody</option>
                        {props.members
                          .filter((m) => m.is_active)
                          .map((m) => (
                            <option key={m.user.id} value={m.user.id}>
                              {[m.user.first_name, m.user.last_name].filter(Boolean).join(" ") || m.user.email}
                            </option>
                          ))}
                      </select>
                    </label>
                  ) : (
                    me &&
                    item.owner !== me.id && (
                      <button type="button" className="link" onClick={() => save({ owner: me.id })}>
                        Make me the owner
                      </button>
                    )
                  )}
                  <label>
                    Due
                    <input
                      type="date"
                      aria-label="Due date"
                      value={item.due_date ?? ""}
                      onChange={(e) => save({ due_date: e.target.value || null })}
                    />
                  </label>
                </div>
              )}
              <label>
                Notes
                <textarea
                  rows={2}
                  aria-label="Notes"
                  value={notes}
                  readOnly={!editable}
                  onChange={(e) => setNotes(e.target.value)}
                  onBlur={() => notes !== item.notes && save({ notes })}
                />
              </label>

              <div>
                <strong className="small">Documents</strong>
                <ul className="small">
                  {item.attachments.map((a) => (
                    <li key={a.id}>
                      <button
                        type="button"
                        className="link"
                        onClick={async () => {
                          try {
                            saveBlob(await api.downloadChecklistAttachment(a.id), a.name);
                          } catch (err) {
                            props.onError(err);
                          }
                        }}
                      >
                        {a.name}
                      </button>{" "}
                      ({Math.ceil(a.size / 1024)} KB)
                      {editable && (
                        <button
                          type="button"
                          className="link"
                          aria-label={`Remove ${a.name}`}
                          onClick={async () => {
                            if (!window.confirm(`Remove ${a.name}?`)) return;
                            try {
                              await api.deleteChecklistAttachment(a.id);
                              props.onReload();
                            } catch (err) {
                              props.onError(err);
                            }
                          }}
                        >
                          remove
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
                {editable && (
                  <input
                    type="file"
                    aria-label={`Attach a document to ${item.title}`}
                    onChange={async (e) => {
                      const file = e.target.files?.[0];
                      if (!file) return;
                      try {
                        props.onChanged(await api.uploadChecklistAttachment(item.id, file));
                      } catch (err) {
                        props.onError(err);
                      }
                      e.target.value = "";
                    }}
                  />
                )}
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
