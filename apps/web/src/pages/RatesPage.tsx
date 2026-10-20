import type { BettermentScheme, PropertyUse, RateStatus, RegisterImport, RegisterProperty } from "@spatial/map-core";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { ErrorMessage } from "../components/ErrorMessage";
import { useLoad } from "../components/useLoad";
import { saveBlob } from "../components/workspace/ExportDialog";
import { useSession } from "../session";

const USES: [PropertyUse, string][] = [
  ["residential", "Residential"],
  ["commercial", "Commercial"],
  ["industrial", "Industrial"],
  ["mixed", "Mixed use"],
  ["institutional", "Institutional"],
  ["vacant", "Vacant land"],
  ["other", "Other"],
];
const STATUS: Record<RateStatus, [string, string]> = {
  never_billed: ["Never billed", "bad"],
  unpaid: ["Owing", "warn"],
  paid: ["Paid up", "ok"],
};
const THIS_YEAR = new Date().getFullYear();

function ghs(value: string | null | undefined): string {
  return value === null || value === undefined ? "—" : `GHS ${Number(value).toLocaleString("en-GH", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function ImportResult({ result }: { result: RegisterImport }) {
  return (
    <div role="status" className="small">
      {result.matched} of {result.rows} rows matched a property.
      {result.unmatched_count > 0 && (
        <>
          {" "}
          {result.unmatched_count} did not:{" "}
          {result.unmatched
            .slice(0, 10)
            .map((u) => `row ${u.row} (${u.reference || "no reference"}${u.reason ? `: ${u.reason}` : ""})`)
            .join(", ")}
          {result.unmatched_count > 10 ? "…" : ""}
        </>
      )}
    </div>
  );
}

function PropertyRow({ prop, canManage, onChanged }: { prop: RegisterProperty; canManage: boolean; onChanged(p: RegisterProperty): void }) {
  const { api } = useSession();
  const [open, setOpen] = useState(false);
  const [values, setValues] = useState({ owner_name: prop.owner_name === "restricted" ? "" : prop.owner_name, use: prop.use, rateable_value: prop.rateable_value ?? "", valuation_ref: prop.valuation_ref, revenue_ref: prop.revenue_ref });
  const [payment, setPayment] = useState("");
  const [error, setError] = useState<unknown>(null);
  const latest = prop.bills[0];
  const [label, tone] = STATUS[prop.status];

  async function save(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const data: Parameters<typeof api.updateProperty>[1] = { use: values.use, rateable_value: values.rateable_value === "" ? null : values.rateable_value, valuation_ref: values.valuation_ref, revenue_ref: values.revenue_ref };
      if (prop.owner_name !== "restricted") data.owner_name = values.owner_name;
      onChanged(await api.updateProperty(prop.id, data));
      setOpen(false);
    } catch (err) {
      setError(err);
    }
  }

  async function pay() {
    if (!latest) return;
    setError(null);
    try {
      onChanged(await api.recordRatePayment(prop.id, { year: latest.year, amount: payment }));
      setPayment("");
    } catch (err) {
      setError(err);
    }
  }

  return (
    <>
      <tr>
        <td>
          <button type="button" className="link" aria-expanded={open} onClick={() => setOpen(!open)}>
            {prop.number}
          </button>
          <div className="muted small">{prop.address}</div>
        </td>
        <td>{prop.use_label}</td>
        <td>{prop.owner_name === "restricted" ? <span className="muted">restricted</span> : prop.owner_name || "—"}</td>
        <td>{ghs(prop.rateable_value)}</td>
        <td>{latest ? `${ghs(latest.amount)} (${latest.year})` : "—"}</td>
        <td>{latest ? ghs(latest.paid) : "—"}</td>
        <td>
          <span className={`pill ${tone}`}>{label}</span>
        </td>
      </tr>
      {open && (
        <tr>
          <td colSpan={7}>
            <ErrorMessage error={error} />
            <form className="inline-form" aria-label={`Property ${prop.number}`} onSubmit={save}>
              {prop.owner_name !== "restricted" && (
                <label>
                  Owner or ratepayer
                  <input aria-label="Owner or ratepayer" disabled={!canManage} value={values.owner_name} onChange={(e) => setValues({ ...values, owner_name: e.target.value })} />
                </label>
              )}
              <label>
                Use
                <select aria-label="Use" disabled={!canManage} value={values.use} onChange={(e) => setValues({ ...values, use: e.target.value as PropertyUse })}>
                  {USES.map(([code, text]) => (
                    <option key={code} value={code}>
                      {text}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Rateable value (GHS)
                <input aria-label="Rateable value" inputMode="decimal" disabled={!canManage} value={values.rateable_value} onChange={(e) => setValues({ ...values, rateable_value: e.target.value })} />
              </label>
              <label>
                Valuation reference
                <input aria-label="Valuation reference" disabled={!canManage} value={values.valuation_ref} onChange={(e) => setValues({ ...values, valuation_ref: e.target.value })} />
              </label>
              <label>
                Revenue account
                <input aria-label="Revenue account" disabled={!canManage} value={values.revenue_ref} onChange={(e) => setValues({ ...values, revenue_ref: e.target.value })} />
              </label>
              {canManage && <button type="submit">Save</button>}
            </form>
            {canManage && latest && Number(latest.owing) > 0 && (
              <div className="inline-form">
                <label>
                  Payment for {latest.year} (GHS), {ghs(latest.owing)} owing
                  <input aria-label={`Payment for ${prop.number}`} inputMode="decimal" value={payment} onChange={(e) => setPayment(e.target.value)} />
                </label>
                <button type="button" className="secondary" disabled={!payment} onClick={() => void pay()}>
                  Record the payment
                </button>
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  );
}

function Rates({ canManage }: { canManage: boolean }) {
  const { api, districtId } = useSession();
  const bands = useLoad(() => api.listRateBands(), [api, districtId]);
  const [values, setValues] = useState({ year: String(THIS_YEAR), use: "residential" as PropertyUse, impost: "", minimum: "", flat: "" });
  const [error, setError] = useState<unknown>(null);

  async function add(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await api.createRateBand({ year: Number(values.year), use: values.use, impost: values.impost, minimum: values.minimum || "0", flat: values.flat || null });
      setValues({ ...values, impost: "", minimum: "", flat: "" });
      bands.reload();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <section aria-label="Rates" className="card wide">
      <h2>Rates</h2>
      <p className="muted small">
        From the Assembly's fee-fixing resolution: for each use and year, the rate as a share of the rateable value (the impost, e.g. 0.005), a
        minimum, and a flat rate for property not yet valued.
      </p>
      <ErrorMessage error={error ?? bands.error} />
      {bands.data && bands.data.length > 0 && (
        <table className="data">
          <thead>
            <tr>
              <th>Year</th>
              <th>Use</th>
              <th>Impost</th>
              <th>Minimum</th>
              <th>Not yet valued</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {bands.data.map((band) => (
              <tr key={band.id}>
                <td>{band.year}</td>
                <td>{USES.find(([code]) => code === band.use)?.[1]}</td>
                <td>{band.impost}</td>
                <td>{ghs(band.minimum)}</td>
                <td>{band.flat ? ghs(band.flat) : "—"}</td>
                <td className="actions">
                  {canManage && (
                    <button type="button" className="link danger" onClick={async () => (await api.deleteRateBand(band.id), bands.reload())}>
                      Remove
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {canManage && (
        <form className="inline-form" aria-label="Add a rate" onSubmit={add}>
          <label>
            Year
            <input aria-label="Year" type="number" style={{ width: "6rem" }} value={values.year} onChange={(e) => setValues({ ...values, year: e.target.value })} />
          </label>
          <label>
            Use
            <select aria-label="Rate use" value={values.use} onChange={(e) => setValues({ ...values, use: e.target.value as PropertyUse })}>
              {USES.map(([code, text]) => (
                <option key={code} value={code}>
                  {text}
                </option>
              ))}
            </select>
          </label>
          <label>
            Impost
            <input aria-label="Impost" required inputMode="decimal" placeholder="0.005" style={{ width: "7rem" }} value={values.impost} onChange={(e) => setValues({ ...values, impost: e.target.value })} />
          </label>
          <label>
            Minimum (GHS)
            <input aria-label="Minimum" inputMode="decimal" style={{ width: "7rem" }} value={values.minimum} onChange={(e) => setValues({ ...values, minimum: e.target.value })} />
          </label>
          <label>
            Not yet valued (GHS)
            <input aria-label="Flat rate" inputMode="decimal" style={{ width: "7rem" }} value={values.flat} onChange={(e) => setValues({ ...values, flat: e.target.value })} />
          </label>
          <button type="submit">Add the rate</button>
        </form>
      )}
    </section>
  );
}

function Scheme({ scheme, canManage, onChanged }: { scheme: BettermentScheme; canManage: boolean; onChanged(s: BettermentScheme): void }) {
  const { api } = useSession();
  const [error, setError] = useState<unknown>(null);
  const [note, setNote] = useState<string | null>(null);
  const detail = useLoad(() => api.getBetterment(scheme.id), [api, scheme.id, scheme]);
  const full = detail.data;

  const act = async (action: () => Promise<BettermentScheme>, done: string) => {
    setError(null);
    setNote(null);
    try {
      const next = await action();
      onChanged(next);
      setNote(done + (next.found ? ` ${next.found.found} properties within ${next.reach_m} m; ${next.found.added} added.` : ""));
    } catch (err) {
      setError(err);
    }
  };
  const clocks = scheme.clocks;

  return (
    <article className="stack" aria-label={scheme.name}>
      <h3>
        {scheme.name} <span className="muted small">· completed {scheme.completed_on}</span>
      </h3>
      <p className="small">
        {scheme.basis === "sum" ? `${ghs(scheme.amount)} on each property` : `${Number(scheme.amount) * 100}% of each property's increase in value`} within{" "}
        {scheme.reach_m} m of the works. {scheme.charges_count} properties, {ghs(scheme.total)} charged, {ghs(scheme.collected)} collected.
      </p>
      <p className={`small ${clocks.overdue ? "error" : "muted"}`}>
        Assessment notices (Form 41) to be served by {clocks.serve_by} ({clocks.rule}): {clocks.unserved} not served yet
        {clocks.served_late ? `, ${clocks.served_late} served late` : ""}.
      </p>
      <ErrorMessage error={error} />
      {note && <p role="status">{note}</p>}
      <div className="inline-form">
        {canManage && (
          <button type="button" onClick={() => void act(() => api.findBettered(scheme.id), "Search done.")} disabled={scheme.works_feature === null}>
            Find the bettered properties
          </button>
        )}
        <button type="button" className="secondary" onClick={async () => saveBlob(await api.bettermentNotice(scheme.id), `betterment-notice-${scheme.id}.pdf`)}>
          Download the notice (Form 40)
        </button>
        {canManage &&
          clocks.published
            .filter((p) => !p.on)
            .map((p) => (
              <button key={p.code} type="button" className="secondary" title={p.label} onClick={() => void act(() => api.publishBetterment(scheme.id, p.code), "Publication recorded.")}>
                Published today: {p.code === "data_room" ? "Data Room" : p.code}
              </button>
            ))}
      </div>
      {scheme.works_feature === null && <p className="muted small">Give the works' feature number to find the properties it bettered.</p>}
      {full?.charges && full.charges.length > 0 && (
        <table className="data" aria-label={`Charges of ${scheme.name}`}>
          <thead>
            <tr>
              <th>Property</th>
              <th>Distance</th>
              {scheme.basis === "rate" && <th>Increase</th>}
              <th>Charge</th>
              <th>Served</th>
              <th>Paid</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {full.charges.map((charge) => (
              <tr key={charge.id}>
                <td>
                  {charge.number}
                  <div className="muted small">{charge.address}</div>
                </td>
                <td>{charge.distance_m} m</td>
                {scheme.basis === "rate" && (
                  <td>
                    {canManage ? (
                      <input
                        aria-label={`Increase in value of ${charge.number}`}
                        inputMode="decimal"
                        style={{ width: "8rem" }}
                        defaultValue={charge.increase ?? ""}
                        onBlur={async (e) => {
                          if (e.target.value === (charge.increase ?? "")) return;
                          await api.updateCharge(charge.id, { increase: e.target.value || null });
                          detail.reload();
                        }}
                      />
                    ) : (
                      ghs(charge.increase)
                    )}
                  </td>
                )}
                <td>{ghs(charge.amount)}</td>
                <td>
                  {charge.served_on ??
                    (canManage ? (
                      <button type="button" className="link" onClick={async () => (await api.updateCharge(charge.id, { served_on: new Date().toISOString().slice(0, 10) }), detail.reload(), onChanged(await api.getBetterment(scheme.id)))}>
                        Served today
                      </button>
                    ) : (
                      "—"
                    ))}
                </td>
                <td>{ghs(charge.paid)}</td>
                <td className="actions">
                  <button type="button" className="link" disabled={charge.amount === null} onClick={async () => saveBlob(await api.chargePaper(charge.id, "assessment"), `betterment-assessment-${charge.number}.pdf`)}>
                    Form 41
                  </button>
                  <button type="button" className="link" disabled={charge.amount === null} onClick={async () => saveBlob(await api.chargePaper(charge.id, "certificate"), `betterment-certificate-${charge.number}.pdf`)}>
                    Certificate
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </article>
  );
}

function Betterment({ projectId, canManage }: { projectId: number; canManage: boolean }) {
  const { api, districtId } = useSession();
  const list = useLoad(() => api.listBetterment(projectId), [api, projectId, districtId]);
  const [schemes, setSchemes] = useState<BettermentScheme[]>([]);
  const [adding, setAdding] = useState(false);
  const [values, setValues] = useState({ name: "", works: "", works_feature: "", reach_m: "100", completed_on: "", basis: "sum" as "sum" | "rate", amount: "" });
  const [error, setError] = useState<unknown>(null);
  useEffect(() => setSchemes(list.data?.results ?? []), [list.data]);

  async function create(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const made = await api.createBetterment({
        project: projectId,
        name: values.name,
        works: values.works,
        works_feature: values.works_feature ? Number(values.works_feature) : null,
        reach_m: values.reach_m,
        completed_on: values.completed_on,
        basis: values.basis,
        amount: values.amount,
      });
      setSchemes([made, ...schemes]);
      setAdding(false);
    } catch (err) {
      setError(err);
    }
  }

  return (
    <section aria-label="Betterment" className="card wide">
      <h2>Betterment</h2>
      <p className="muted small">
        Where public works (a road, a drain) raise the value of land, the Assembly fixes a charge on the properties bettered (L.I. 2384 r.40):
        a notice published (Form 40), then an assessment served on each owner within 90 days of completion (Form 41). A certificate of the sum
        due is evidence for recovering it as a civil debt (r.41).
      </p>
      <ErrorMessage error={error ?? list.error} />
      {schemes.length === 0 && <p className="muted">No betterment schemes yet.</p>}
      {schemes.map((scheme) => (
        <Scheme key={scheme.id} scheme={scheme} canManage={canManage} onChanged={(next) => setSchemes(schemes.map((s) => (s.id === next.id ? next : s)))} />
      ))}
      {canManage && !adding && (
        <div className="inline-form">
          <button type="button" className="secondary" onClick={() => setAdding(true)}>
            Add a betterment scheme
          </button>
        </div>
      )}
      {adding && (
        <form className="stack" aria-label="New betterment scheme" onSubmit={create}>
          <div className="inline-form">
            <label>
              Works
              <input required aria-label="Works" placeholder="e.g. Main Street paving" value={values.name} onChange={(e) => setValues({ ...values, name: e.target.value })} />
            </label>
            <label>
              Completed on
              <input required type="date" aria-label="Completed on" value={values.completed_on} onChange={(e) => setValues({ ...values, completed_on: e.target.value })} />
            </label>
            <label>
              Feature number of the works on the map
              <input aria-label="Works feature" inputMode="numeric" style={{ width: "8rem" }} value={values.works_feature} onChange={(e) => setValues({ ...values, works_feature: e.target.value })} />
            </label>
            <label>
              Bettered within (m)
              <input aria-label="Within" inputMode="decimal" style={{ width: "6rem" }} value={values.reach_m} onChange={(e) => setValues({ ...values, reach_m: e.target.value })} />
            </label>
          </div>
          <div className="inline-form">
            <label>
              Charge
              <select aria-label="Charge" value={values.basis} onChange={(e) => setValues({ ...values, basis: e.target.value as "sum" | "rate" })}>
                <option value="sum">A fixed sum on each property</option>
                <option value="rate">A share of each property's increase in value</option>
              </select>
            </label>
            <label>
              {values.basis === "sum" ? "Sum (GHS)" : "Share (e.g. 0.25)"}
              <input required aria-label="Amount" inputMode="decimal" style={{ width: "8rem" }} value={values.amount} onChange={(e) => setValues({ ...values, amount: e.target.value })} />
            </label>
          </div>
          <label>
            Description of the works
            <input aria-label="Description of the works" value={values.works} onChange={(e) => setValues({ ...values, works: e.target.value })} />
          </label>
          <p className="muted small">The feature number is shown when you click the road or drain on the project's map with Identify.</p>
          <div className="inline-form">
            <button type="submit">Add the scheme</button>
            <button type="button" className="link" onClick={() => setAdding(false)}>
              Cancel
            </button>
          </div>
        </form>
      )}
    </section>
  );
}

/** A project's property register, rates and bills, its link to the revenue system, and betterment. */
export function RatesPage() {
  const { projectId } = useParams();
  const id = Number(projectId);
  const { api, can, districtId } = useSession();
  const canManage = can("revenue.manage");
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const summary = useLoad(() => api.registerSummary(id), [api, id, districtId]);
  const list = useLoad(() => api.listRegister(id, { status: status || undefined, q: q || undefined }), [api, id, districtId, status, q]);
  const [rows, setRows] = useState<RegisterProperty[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [note, setNote] = useState<string | null>(null);
  const [imported, setImported] = useState<RegisterImport | null>(null);
  const [year, setYear] = useState(String(THIS_YEAR));
  useEffect(() => setRows(list.data?.results ?? []), [list.data]);
  const s = summary.data;

  const run = async (action: () => Promise<string>) => {
    setError(null);
    setNote(null);
    setImported(null);
    try {
      setNote(await action());
      summary.reload();
      list.reload();
    } catch (err) {
      setError(err);
    }
  };

  async function importFile(what: "valuations" | "revenue", file: File | undefined) {
    if (!file) return;
    setError(null);
    setNote(null);
    try {
      setImported(await api.importRegister(id, what, file));
      summary.reload();
      list.reload();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <section className="page">
      <p>
        <Link to={`/projects/${id}`}>← Back to the project</Link>
      </p>
      <h1>Property rates and betterment</h1>
      <p className="muted">
        The register of rateable properties, built from the map; their valuations and bills; the link to the Assembly's revenue system; and the
        map of what has never been billed and what is owing. Only the Assembly may levy rates in the district (Local Governance Act, 2016).
      </p>
      <ErrorMessage error={error ?? summary.error} />
      {note && <p role="status">{note}</p>}
      {imported && <ImportResult result={imported} />}
      {s && (
        <dl className="facts" aria-label="Register">
          <dt>Properties</dt>
          <dd>
            {s.properties} <span className="muted small">({s.valued} valued)</span>
          </dd>
          <dt>Never billed</dt>
          <dd className={s.by_status.never_billed ? "error" : undefined}>{s.by_status.never_billed}</dd>
          <dt>Owing</dt>
          <dd>
            {s.by_status.unpaid} <span className="muted small">({ghs(s.owing)})</span>
          </dd>
          <dt>Paid up</dt>
          <dd>{s.by_status.paid}</dd>
          <dt>Billed and collected</dt>
          <dd>
            {ghs(s.billed)} billed, {ghs(s.paid)} collected{s.collected_pct !== null ? ` (${s.collected_pct}%)` : ""}
          </dd>
        </dl>
      )}

      {canManage && (
        <section aria-label="Register tasks" className="card wide">
          <h2>Keep the register</h2>
          <div className="inline-form">
            <button type="button" onClick={() => void run(async () => {
              const r = await api.buildRegister(id);
              return `${r.added} properties added from the map; ${r.total} in the register.`;
            })}>
              Add properties from the map
            </button>
            <label>
              Year
              <input aria-label="Bill year" type="number" style={{ width: "6rem" }} value={year} onChange={(e) => setYear(e.target.value)} />
            </label>
            <button type="button" className="secondary" onClick={() => void run(async () => {
              const r = await api.billYear(id, Number(year));
              return `${r.billed} bills made (${ghs(r.total)}).` + (r.skipped_count ? ` ${r.skipped_count} not billed: ${r.skipped.slice(0, 3).map((x) => `${x.number}: ${x.reason}`).join("; ")}` : "");
            })}>
              Bill the year
            </button>
            <button type="button" className="secondary" onClick={() => void run(async () => {
              const r = await api.mapRegister(id);
              return `The "Property rates" layer on the project's map is up to date (${r.written} changed).`;
            })}>
              Show on the map
            </button>
            <button type="button" className="secondary" onClick={async () => saveBlob(await api.registerCsv(id), `property-register-${id}.csv`)}>
              Download for the revenue system
            </button>
          </div>
          <div className="inline-form">
            <label>
              Valuation list (CSV: number or valuation_ref, rateable_value, valued_on, owner)
              <input type="file" accept=".csv,text/csv" aria-label="Valuation list" onChange={(e) => void importFile("valuations", e.target.files?.[0])} />
            </label>
            <label>
              From the revenue system (CSV: property or revenue_ref, year, bill, amount, paid, paid_on)
              <input type="file" accept=".csv,text/csv" aria-label="Bills and payments" onChange={(e) => void importFile("revenue", e.target.files?.[0])} />
            </label>
          </div>
        </section>
      )}

      <div className="inline-form">
        <label>
          Show
          <select aria-label="Show" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All properties</option>
            <option value="never_billed">Never billed</option>
            <option value="unpaid">Owing</option>
            <option value="paid">Paid up</option>
          </select>
        </label>
        <label>
          Find
          <input aria-label="Find" placeholder="Number, address or account" value={q} onChange={(e) => setQ(e.target.value)} />
        </label>
      </div>
      <ErrorMessage error={list.error} />
      {list.data && rows.length === 0 && <p className="muted">{status || q ? "No property matches." : "No properties in the register yet: add them from the map."}</p>}
      {rows.length > 0 && (
        <table className="data" aria-label="Properties">
          <thead>
            <tr>
              <th>Property</th>
              <th>Use</th>
              <th>Owner</th>
              <th>Rateable value</th>
              <th>Last bill</th>
              <th>Paid</th>
              <th>Rates</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((prop) => (
              <PropertyRow key={prop.id} prop={prop} canManage={canManage} onChanged={(next) => (setRows(rows.map((r) => (r.id === next.id ? next : r))), summary.reload())} />
            ))}
          </tbody>
        </table>
      )}
      {list.data && list.data.count > rows.length && <p className="muted small">Showing {rows.length} of {list.data.count}; use Find to narrow.</p>}

      <Rates canManage={canManage} />
      <Betterment projectId={id} canManage={canManage} />
    </section>
  );
}
