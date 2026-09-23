import type { AuditAction, AuditEntry, AuditFilters } from "@spatial/map-core";
import { Fragment, useState } from "react";

import { ErrorMessage } from "../components/ErrorMessage";
import { useLoad } from "../components/useLoad";
import { useSession } from "../session";

const TABLE_LABELS: Record<string, string> = {
  core_user: "User",
  core_membership: "Membership",
  core_district: "District",
  core_region: "Region",
};

export function AuditPage() {
  const { api, districtId } = useSession();
  const [filters, setFilters] = useState<AuditFilters>({ page: 1 });
  const [open, setOpen] = useState<number | null>(null);
  const { data, error, loading } = useLoad(() => api.listAudit(filters), [api, districtId, filters]);

  const update = (change: Partial<AuditFilters>) => setFilters((f) => ({ ...f, ...change, page: change.page ?? 1 }));
  const page = filters.page ?? 1;

  return (
    <section className="page">
      <h1>Audit log</h1>
      <div className="inline-form">
        <select aria-label="Record type" value={filters.table ?? ""} onChange={(e) => update({ table: e.target.value || undefined })}>
          <option value="">All record types</option>
          {Object.entries(TABLE_LABELS).map(([table, label]) => (
            <option key={table} value={table}>
              {label}
            </option>
          ))}
        </select>
        <select
          aria-label="Change type"
          value={filters.action ?? ""}
          onChange={(e) => update({ action: (e.target.value || undefined) as AuditAction | undefined })}
        >
          <option value="">All changes</option>
          <option value="INSERT">Created</option>
          <option value="UPDATE">Changed</option>
          <option value="DELETE">Deleted</option>
        </select>
      </div>
      <ErrorMessage error={error} />
      {loading && !data ? (
        <p>Loading…</p>
      ) : (
        <>
          <table className="data">
            <thead>
              <tr>
                <th>When</th>
                <th>Who</th>
                <th>Record</th>
                <th>Change</th>
                <th>Fields</th>
              </tr>
            </thead>
            <tbody>
              {data?.results.map((entry) => (
                <Fragment key={entry.id}>
                  <tr className="clickable" onClick={() => setOpen(open === entry.id ? null : entry.id)}>
                    <td>{new Date(entry.occurred_at).toLocaleString()}</td>
                    <td>{entry.user_email ?? "system"}</td>
                    <td>
                      {TABLE_LABELS[entry.table_name] ?? entry.table_name} #{entry.row_id}
                    </td>
                    <td>{entry.action}</td>
                    <td>{entry.changed_fields.join(", ")}</td>
                  </tr>
                  {open === entry.id && (
                    <tr>
                      <td colSpan={5}>
                        <ChangeDetail entry={entry} />
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
          <div className="pager">
            <button type="button" disabled={!data?.previous} onClick={() => update({ page: page - 1 })}>
              Previous
            </button>
            <span>
              Page {page} · {data?.count ?? 0} entries
            </span>
            <button type="button" disabled={!data?.next} onClick={() => update({ page: page + 1 })}>
              Next
            </button>
          </div>
        </>
      )}
    </section>
  );
}

function show(value: unknown): string {
  return value === undefined ? "—" : JSON.stringify(value);
}

function ChangeDetail({ entry }: { entry: AuditEntry }) {
  return (
    <table className="detail">
      <thead>
        <tr>
          <th>Field</th>
          <th>Before</th>
          <th>After</th>
        </tr>
      </thead>
      <tbody>
        {entry.changed_fields.map((field) => (
          <tr key={field}>
            <td>{field}</td>
            <td>{show(entry.before?.[field])}</td>
            <td>{show(entry.after?.[field])}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
