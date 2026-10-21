import type { SetupStep, WorkItem, WorkKind, WorkList as Work } from "@spatial/map-core";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { Icon } from "./Icon";
import { OfficerPicker } from "./OfficerPicker";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function shortDate(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return `${d} ${MONTHS[(m ?? 1) - 1]} ${y}`;
}

/** "5 days late", "Due today", "Due in 3 days", or the date. */
export function Due({ item }: { item: Pick<WorkItem, "days" | "due_on" | "overdue"> }) {
  const { days, due_on: due } = item;
  if (due === null || days === null) return <span className="pill">No date</span>;
  if (item.overdue || days < 0) {
    const late = Math.max(1, -days);
    return (
      <span className="pill bad" title={`Was due ${shortDate(due)}`}>
        {late} day{late === 1 ? "" : "s"} late
      </span>
    );
  }
  if (days === 0) return <span className="pill warn">Due today</span>;
  if (days <= 7)
    return (
      <span className="pill warn" title={shortDate(due)}>
        Due in {days} day{days === 1 ? "" : "s"}
      </span>
    );
  return <span className="pill">Due {shortDate(due)}</span>;
}

type Tab = "mine" | "all" | "late" | "week";

const KIND_LABELS: Record<WorkKind, string> = {
  permit: "Permit applications",
  challenge: "Reviews and appeals",
  land: "Land applications",
  case: "Enforcement cases",
  request: "Requests for information",
  meeting: "Committee meetings",
  zoning: "Zoning schemes",
};

/** Everything with a next step, across the modules, the most pressing first. */
export function WorkList({ work, me, onChanged }: { work: Work; me: number | undefined; onChanged?: () => void }) {
  const { counts, items } = work;
  const [tab, setTab] = useState<Tab>(counts.mine > 0 ? "mine" : "all");
  const [kind, setKind] = useState<WorkKind | "">("");
  const [limit, setLimit] = useState(15);

  const kinds = useMemo(() => Array.from(new Set(items.map((i) => i.kind))), [items]);
  const shown = items.filter((i) => {
    if (kind && i.kind !== kind) return false;
    if (tab === "mine") return i.officer?.id === me;
    if (tab === "late") return i.overdue;
    if (tab === "week") return !i.overdue && i.days !== null && i.days <= 7;
    return true;
  });

  const tabs: { code: Tab; label: string; count: number }[] = [
    { code: "mine", label: "Assigned to me", count: counts.mine },
    { code: "late", label: "Late", count: counts.overdue },
    { code: "week", label: "Due this week", count: counts.this_week },
    { code: "all", label: "Everything", count: counts.all },
  ];

  return (
    <section className="card wide work" aria-label="Your work">
      <div className="work-head">
        <h2>Your work</h2>
        <div className="segmented" role="group" aria-label="Show">
          {tabs.map((t) => (
            <button key={t.code} type="button" aria-pressed={tab === t.code} onClick={() => (setTab(t.code), setLimit(15))}>
              {t.label} <span className={`count${t.code === "late" && t.count ? " bad" : ""}`}>{t.count}</span>
            </button>
          ))}
        </div>
        {kinds.length > 1 && (
          <label className="inline">
            <span className="visually-hidden">Kind of record</span>
            <select aria-label="Kind of record" value={kind} onChange={(e) => setKind(e.target.value as WorkKind | "")}>
              <option value="">All kinds</option>
              {kinds.map((k) => (
                <option key={k} value={k}>
                  {KIND_LABELS[k]}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      {shown.length === 0 ? (
        <p className="empty">
          {tab === "mine"
            ? counts.unassigned
              ? `Nothing is assigned to you yet. ${counts.unassigned} record${counts.unassigned === 1 ? " is" : "s are"} waiting for an officer: choose one under "Everything".`
              : "Nothing is assigned to you."
            : tab === "late"
              ? "Nothing is past its statutory date."
              : tab === "week"
                ? "Nothing falls due in the next seven days."
                : "Nothing is waiting: every application, case and request is up to date."}
        </p>
      ) : (
        <ul className="work-items">
          {shown.slice(0, limit).map((item) => (
            <li key={`${item.kind}-${item.id}-${item.step}`} className={item.overdue ? "late" : undefined}>
              <span className="work-due">
                <Due item={item} />
              </span>
              <span className="work-main">
                <Link to={item.link}>
                  <span className="work-kind">{item.kind_label}</span> <strong>{item.number}</strong>
                </Link>
                <span className="muted">
                  {item.title}
                  {item.who ? ` · ${item.who}` : ""}
                </span>
              </span>
              <span className="work-step">
                <Icon name="chevronRight" size={14} />
                {item.step}
                {item.rule && <span className="muted small"> {item.rule}</span>}
              </span>
              <span className="work-officer">
                {item.assignable && (item.kind === "permit" || item.kind === "land" || item.kind === "case") ? (
                  <OfficerPicker kind={item.kind} id={item.id} officer={item.officer} onChange={onChanged} compact />
                ) : (
                  item.officer && <span className="muted small">{item.officer.name}</span>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
      {shown.length > limit && (
        <button type="button" className="link" onClick={() => setLimit((n) => n + 30)}>
          Show more ({shown.length - limit} more)
        </button>
      )}
    </section>
  );
}

/** What a new district still has to set up, each with where to do it. */
export function SetupChecklist({ steps }: { steps: SetupStep[] }) {
  const done = steps.filter((s) => s.done).length;
  if (done === steps.length) return null;
  const next = steps.find((s) => !s.done);
  return (
    <section className="card wide setup" aria-label="Setting up the district">
      <div className="work-head">
        <h2>Setting up the district</h2>
        <span className="muted">
          {done} of {steps.length} done
        </span>
      </div>
      <div className="progress" aria-hidden="true">
        <div style={{ width: `${(100 * done) / steps.length}%` }} />
      </div>
      <ol className="setup-steps">
        {steps.map((s) => (
          <li key={s.code} className={s.done ? "done" : s === next ? "next" : undefined}>
            <span className="setup-mark" aria-label={s.done ? "Done" : "To do"}>
              {s.done ? <Icon name="check" size={16} /> : null}
            </span>
            <span>
              <Link to={s.link}>{s.label}</Link>
              <span className="muted small">{s.hint}</span>
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}
