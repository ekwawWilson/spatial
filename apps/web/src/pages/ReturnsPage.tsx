import type { ExchangeKey } from "@spatial/map-core";
import { useState, type FormEvent } from "react";

import { ErrorMessage } from "../components/ErrorMessage";
import { useLoad } from "../components/useLoad";
import { saveBlob } from "../components/workspace/ExportDialog";
import { useSession } from "../session";

function lastQuarter(today = new Date()): string {
  const quarter = Math.floor(today.getMonth() / 3); // 0 means the previous year's 4th
  return quarter === 0 ? `${today.getFullYear() - 1}-Q4` : `${today.getFullYear()}-Q${quarter}`;
}

function periods(today = new Date()): [string, string][] {
  const out: [string, string][] = [];
  for (let year = today.getFullYear(); year >= today.getFullYear() - 2; year--) {
    out.push([String(year), `The year ${year}`]);
    for (let q = 4; q >= 1; q--) out.push([`${year}-Q${q}`, `Quarter ${q} of ${year}`]);
  }
  return out;
}

function pct(value: number | null): string {
  return value === null ? "—" : `${value}%`;
}

function Return() {
  const { api, districtId } = useSession();
  const [period, setPeriod] = useState(lastQuarter());
  const data = useLoad(() => api.districtReturn(period), [api, districtId, period]);
  const r = data.data;

  return (
    <section aria-label="Return" className="card wide">
      <h2>Return of the District Planning Authority</h2>
      <p className="muted small">
        What the Assembly's planning authority did in a quarter or a year, counted from the platform's records: for LUSPA, the Regional
        Coordinating Council and the Assembly's own performance assessment. No names, only figures.
      </p>
      <div className="inline-form">
        <label>
          Period
          <select aria-label="Period" value={period} onChange={(e) => setPeriod(e.target.value)}>
            {periods().map(([code, label]) => (
              <option key={code} value={code}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <button type="button" className="secondary" onClick={async () => saveBlob(await api.districtReturnFile(period, "pdf"), `return-${period}.pdf`)}>
          Download as PDF
        </button>
        <button type="button" className="secondary" onClick={async () => saveBlob(await api.districtReturnFile(period, "csv"), `return-${period}.csv`)}>
          Download as CSV
        </button>
      </div>
      <ErrorMessage error={data.error} />
      {r && (
        <table className="data" aria-label="The return">
          <thead>
            <tr>
              <th>Section</th>
              <th>Measure</th>
              <th>{r.period.label}</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <th rowSpan={4}>Permits</th>
              <td>Applications received (development / planning)</td>
              <td>
                {r.permits.received} ({r.permits.received_by_kind.development} / {r.permits.received_by_kind.planning})
              </td>
            </tr>
            <tr>
              <td>Decided: granted / refused</td>
              <td>
                {r.permits.decided}: {r.permits.granted} / {r.permits.refused}
              </td>
            </tr>
            <tr>
              <td>Certificates issued</td>
              <td>{r.permits.issued}</td>
            </tr>
            <tr>
              <td>Decided within {r.permits.limit_days} days; average days</td>
              <td>
                {pct(r.permits.decided_within_limit_pct)}; {r.permits.average_days_to_decision ?? "—"}
              </td>
            </tr>
            {r.land.map((kind, i) => (
              <tr key={kind.kind}>
                {i === 0 && <th rowSpan={r.land.length}>Land applications</th>}
                <td>{kind.kind}: received / approved / refused</td>
                <td>
                  {kind.received} / {kind.approved} / {kind.refused}
                </td>
              </tr>
            ))}
            <tr>
              <th rowSpan={3}>Enforcement</th>
              <td>Cases opened; notices served</td>
              <td>
                {r.enforcement.cases_opened}; {r.enforcement.notices_served}
              </td>
            </tr>
            <tr>
              <td>Cases closed: by the owner / by the Assembly / no contravention</td>
              <td>
                {r.enforcement.cases_closed}: {r.enforcement.closed_by_outcome.rectified} / {r.enforcement.closed_by_outcome.enforced} /{" "}
                {r.enforcement.closed_by_outcome.dropped}
              </td>
            </tr>
            <tr>
              <td>Cost recovered</td>
              <td>GHS {r.enforcement.cost_recovered}</td>
            </tr>
            <tr>
              <th rowSpan={2}>Local plans</th>
              <td>Commenced / draft on display / approved</td>
              <td>
                {r.plans.commenced.length} / {r.plans.drafts_on_display.length} / {r.plans.approved.length}
                {r.plans.approved.length > 0 && <div className="muted small">Approved: {r.plans.approved.join("; ")}</div>}
              </td>
            </tr>
            <tr>
              <td>Consultations held; comments received</td>
              <td>
                {r.plans.consultations_held}; {r.plans.comments_received}
              </td>
            </tr>
            <tr>
              <th>Public Data Room</th>
              <td>Requests received; answered within 5 days</td>
              <td>
                {r.data_room.requests_received}; {pct(r.data_room.answered_within_limit_pct)}
              </td>
            </tr>
            <tr>
              <th>Rates and betterment</th>
              <td>Bills issued; billed; betterment schemes completed</td>
              <td>
                {r.revenue.bills_issued}; GHS {r.revenue.billed}; {r.revenue.betterment_schemes_completed}
              </td>
            </tr>
          </tbody>
        </table>
      )}
    </section>
  );
}

function Keys() {
  const { api, districtId } = useSession();
  const list = useLoad(() => api.listExchangeKeys(), [api, districtId]);
  const [name, setName] = useState("");
  const [scopes, setScopes] = useState<string[]>(["permits", "plans", "zoning", "returns"]);
  const [made, setMade] = useState<ExchangeKey | null>(null);
  const [error, setError] = useState<unknown>(null);

  async function create(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      // Only what this server offers.
      setMade(await api.createExchangeKey({ name, scopes: scopes.filter((s) => s in (list.data?.scopes ?? {})) }));
      setName("");
      list.reload();
    } catch (err) {
      setError(err);
    }
  }

  const base = `${window.location.origin}/api/exchange/v1/`;
  return (
    <section aria-label="Data exchange" className="card wide">
      <h2>Data exchange with national bodies</h2>
      <p className="muted small">
        A key lets LUSPA, the Lands Commission or the Regional Coordinating Council read the district's records directly, as GeoJSON: only
        what you tick, never names or contacts. Every read is counted and recorded in the audit log. Revoke a key to stop it.
      </p>
      <ErrorMessage error={error ?? list.error} />
      {made?.key && (
        <div role="status">
          <p>
            Key for <strong>{made.name}</strong>. Copy it now and send it to them securely: it is not shown again.
          </p>
          <p>
            <code>{made.key}</code>{" "}
            <button type="button" className="link" onClick={() => void navigator.clipboard?.writeText(made.key!).catch(() => undefined)}>
              Copy
            </button>
          </p>
          <p className="small">
            They read, for example: <code>GET {base}permits/</code> with the header <code>Authorization: Key {made.key.slice(0, 10)}…</code>
          </p>
        </div>
      )}
      {list.data && list.data.keys.length > 0 && (
        <table className="data" aria-label="Keys">
          <thead>
            <tr>
              <th>For</th>
              <th>May read</th>
              <th>Made</th>
              <th>Last used</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {list.data.keys.map((key) => (
              <tr key={key.id} className={key.revoked_at ? "inactive" : undefined}>
                <td>
                  {key.name}
                  <div className="muted small">
                    <code>{key.prefix}…</code>
                  </div>
                </td>
                <td>{key.scopes.join(", ")}</td>
                <td className="small">
                  {key.created_at.slice(0, 10)}
                  {key.created_by && <div className="muted">{key.created_by}</div>}
                </td>
                <td className="small">{key.last_used_at ? `${key.last_used_at.slice(0, 10)} (${key.uses} reads)` : "Never"}</td>
                <td className="actions">
                  {key.revoked_at ? (
                    <span className="pill">Revoked {key.revoked_at.slice(0, 10)}</span>
                  ) : (
                    <button type="button" className="link danger" onClick={async () => (await api.revokeExchangeKey(key.id), list.reload())}>
                      Revoke
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {list.data && (
        <form className="stack" aria-label="New key" onSubmit={create}>
          <h3>Issue a key</h3>
          <label>
            For (the body and office)
            <input required aria-label="For" placeholder="e.g. LUSPA, Accra" value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <fieldset>
            <legend>May read</legend>
            {Object.entries(list.data.scopes).map(([code, label]) => (
              <label key={code} className="checkbox">
                <input type="checkbox" checked={scopes.includes(code)} onChange={(e) => setScopes(e.target.checked ? [...scopes, code] : scopes.filter((s) => s !== code))} />
                {label}
              </label>
            ))}
          </fieldset>
          <div className="inline-form">
            <button type="submit" disabled={scopes.length === 0}>
              Issue the key
            </button>
          </div>
        </form>
      )}
    </section>
  );
}

/** The district's periodic return, and keys for national bodies to read its records. */
export function ReturnsPage() {
  const { can } = useSession();
  return (
    <section className="page">
      <h1>Returns and data exchange</h1>
      <p className="muted">
        The return of the district's planning work for a quarter or a year, and direct access to its records for national bodies.
      </p>
      <Return />
      {can("exchange.manage") && <Keys />}
    </section>
  );
}
