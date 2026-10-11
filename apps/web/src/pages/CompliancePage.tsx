import type { Compliance, LateRow } from "@spatial/map-core";
import { Link } from "react-router-dom";

import { ErrorMessage } from "../components/ErrorMessage";
import { useLoad } from "../components/useLoad";
import { saveBlob } from "../components/workspace/ExportDialog";
import { useSession } from "../session";

function pct(value: number | null): string {
  return value === null ? "—" : `${value}%`;
}

function Row(props: { duty: string; open: number; overdue: number; met: string }) {
  return (
    <tr>
      <th scope="row">{props.duty}</th>
      <td>{props.open}</td>
      <td className={props.overdue ? "error" : undefined}>{props.overdue}</td>
      <td>{props.met}</td>
    </tr>
  );
}

function PermitLink({ row }: { row: LateRow }) {
  return <Link to={`/projects/${row.project}/permits/${row.id}`}>{row.number}</Link>;
}

function Body({ data }: { data: Compliance }) {
  const { permits, requests } = data;
  return (
    <>
      <p role="status" className={data.overdue ? "error" : undefined}>
        {data.overdue === 0 ? "Nothing is past its date." : `${data.overdue} ${data.overdue === 1 ? "duty is" : "duties are"} past the date the Regulations set.`}
      </p>
      <table className="data" aria-label="Duties">
        <thead>
          <tr>
            <th>Duty</th>
            <th>Open</th>
            <th>Past its date</th>
            <th>Met in time this year</th>
          </tr>
        </thead>
        <tbody>
          <Row duty={`Permit applications: decision within ${permits.limit_days} days (r.44)`} open={permits.open} overdue={permits.overdue} met={`${pct(permits.decided_within_limit_pct)} of ${permits.decided_this_year} decided`} />
          <Row duty={`Requests for information: answer within ${requests.limit_days} days (r.64)`} open={requests.open} overdue={requests.overdue} met={`${pct(requests.answered_within_limit_pct)} of ${requests.answered_this_year} answered`} />
          <Row duty="Enforcement cases: the steps of r.57" open={data.enforcement.open} overdue={data.enforcement.overdue} met="—" />
          <Row duty="Zoning schemes: the duties of r.29" open={data.zoning.schemes} overdue={data.zoning.overdue} met="—" />
        </tbody>
      </table>
      <p className="muted small">
        Average time from receipt to decision this year: {permits.average_days_to_decision === null ? "—" : `${permits.average_days_to_decision} days`}. Applications received this
        year: {permits.received_this_year}. The Public Data Room is {data.dataroom.is_open ? "open online" : "not open online"}, with{" "}
        {data.dataroom.published_projects} project(s) published and {data.dataroom.documents_on_display} document(s) on display.
      </p>

      {permits.late.length > 0 && (
        <section aria-label="Permit applications past a deadline" className="card wide">
          <h2>Permit applications past a deadline</h2>
          <table className="data">
            <thead>
              <tr>
                <th>Application</th>
                <th>Step</th>
                <th>Due</th>
                <th>Days late</th>
              </tr>
            </thead>
            <tbody>
              {permits.late.map((row) => (
                <tr key={row.id}>
                  <td>
                    <PermitLink row={row} />
                  </td>
                  <td>
                    {row.step} <span className="muted small">{row.rule}</span>
                  </td>
                  <td>{row.due_on}</td>
                  <td className="error">{row.days_late}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {(data.enforcement.late.length > 0 || data.zoning.late.length > 0) && (
        <section aria-label="Other duties past their date" className="card wide">
          <h2>Enforcement steps and zoning duties past their date</h2>
          <ul>
            {data.enforcement.late.map((row) => (
              <li key={`case-${row.id}`}>
                <Link to={`/projects/${row.project}/enforcement/${row.id}`}>{row.number}</Link>: {row.step}, due {row.due_on}
              </li>
            ))}
            {data.zoning.late.map((row) => (
              <li key={`${row.scheme}-${row.duty}`}>
                <Link to={`/projects/${row.project}/zoning`}>{row.scheme}</Link>: {row.duty}, due {row.due_on} <span className="muted small">{row.rule}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {data.week_ahead.length > 0 && (
        <section aria-label="Due this week" className="card wide">
          <h2>Due in the next seven days</h2>
          <ul>
            {data.week_ahead.map((row) => (
              <li key={row.id}>
                <PermitLink row={row} />: {row.step}, by {row.due_on}
              </li>
            ))}
          </ul>
        </section>
      )}
    </>
  );
}

/** The district's statutory deadlines at a glance, for the department and for management. */
export function CompliancePage() {
  const { api, districtId } = useSession();
  const data = useLoad(() => api.compliance(), [api, districtId]);
  return (
    <section className="page">
      <h1>Statutory deadlines</h1>
      <p className="muted">
        What the Land Use and Spatial Planning Regulations, 2019 (L.I. 2384) ask the Assembly to do by a date, counted from the
        platform's records{data.data && ` as of ${data.data.as_of}`}.
      </p>
      <ErrorMessage error={data.error} />
      {data.data && (
        <>
          <div className="inline-form">
            <button type="button" className="secondary" onClick={async () => saveBlob(await api.compliancePdf(), `statutory-deadlines-${data.data!.as_of}.pdf`)}>
              Download as a page to print
            </button>
          </div>
          <Body data={data.data} />
        </>
      )}
    </section>
  );
}
