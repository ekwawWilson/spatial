import type { AddressingMethod, AddressingOptions } from "@spatial/map-core";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ErrorMessage } from "../components/ErrorMessage";
import { useLoad } from "../components/useLoad";
import { saveBlob } from "../components/workspace/ExportDialog";
import { useSession } from "../session";

/** Street codes and property numbers for a project: proposed first, written to the map when applied. */
export function AddressingPage() {
  const { projectId } = useParams();
  const id = Number(projectId);
  const { api, can, districtId } = useSession();
  const [method, setMethod] = useState<AddressingMethod>("decametric");
  const [oddSide, setOddSide] = useState<"left" | "right">("left");
  const [lat, setLat] = useState("");
  const [lon, setLon] = useState("");
  const [start, setStart] = useState<{ lon: number; lat: number } | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [note, setNote] = useState<string | null>(null);
  const options: AddressingOptions = { method, odd_side: oddSide, ...(start ?? {}) };
  const proposal = useLoad(() => api.proposeAddresses(id, options), [api, id, districtId, method, oddSide, start]);
  const data = proposal.data;

  async function apply() {
    if (!data || !window.confirm(`Write ${data.numbered} property numbers and ${data.new_street_codes.length} street codes to the map?`)) return;
    setError(null);
    setNote(null);
    try {
      const result = await api.applyAddresses(id, options);
      setNote(`Written to the map: ${result.written.properties} property number(s) and ${result.written.streets} street code(s) changed.`);
      proposal.reload();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <section className="page">
      <p>
        <Link to={`/projects/${id}`}>← Back to the project</Link>
      </p>
      <h1>Street addressing</h1>
      <p className="muted">
        A code for every street and a number for every property, from where it stands along its street: odd numbers on one side, even
        on the other (L.I. 2384 r.28). What you see here is a proposal: nothing changes on the map until you apply it.
      </p>
      <ErrorMessage error={error ?? proposal.error} />
      {note && <p role="status">{note}</p>}

      <form
        className="card wide stack"
        aria-label="Numbering"
        onSubmit={(e) => {
          e.preventDefault();
          setStart(lat && lon ? { lon: Number(lon), lat: Number(lat) } : null);
        }}
      >
        <h2>How to number</h2>
        <div className="inline-form">
          <label>
            Numbers
            <select aria-label="Numbers" value={method} onChange={(e) => setMethod(e.target.value as AddressingMethod)}>
              <option value="decametric">By distance, every 10 m</option>
              <option value="metric">By distance, every metre</option>
              <option value="sequential">One after another along the street</option>
            </select>
          </label>
          <label>
            Odd numbers on the
            <select aria-label="Odd numbers on the" value={oddSide} onChange={(e) => setOddSide(e.target.value as "left" | "right")}>
              <option value="left">Left of the street</option>
              <option value="right">Right of the street</option>
            </select>
          </label>
        </div>
        <div className="inline-form">
          <label>
            Start each street from the end nearer (optional): latitude
            <input aria-label="Start latitude" inputMode="decimal" value={lat} onChange={(e) => setLat(e.target.value)} placeholder="e.g. the town centre" />
          </label>
          <label>
            longitude
            <input aria-label="Start longitude" inputMode="decimal" value={lon} onChange={(e) => setLon(e.target.value)} />
          </label>
          <button type="submit" className="secondary">
            Use this start
          </button>
        </div>
        <p className="muted small">
          Left and right are as you travel from the street's start. Without a start place, each street starts at the end it was drawn
          from. By distance, a number says roughly how far along the street a property is, so a new building between two others gets a
          number in between and nothing is renumbered. Set these to the national manual's rules for your district before applying.
        </p>
      </form>

      {data && (
        <>
          <dl className="facts" aria-label="Summary">
            <dt>Streets</dt>
            <dd>
              {data.streets}
              {data.new_street_codes.length > 0 && `, ${data.new_street_codes.length} to be given a code`}
              {data.streets_without_a_name > 0 && <span className="error">, {data.streets_without_a_name} without a name</span>}
            </dd>
            <dt>Properties numbered</dt>
            <dd>
              {data.numbered} of {data.properties}
            </dd>
            <dt>Too far from any street</dt>
            <dd className={data.without_a_street ? "error" : undefined}>{data.without_a_street ?? "—"}</dd>
            <dt>Numbers that would change</dt>
            <dd>{data.changes}</dd>
          </dl>
          <div className="inline-form">
            <button type="button" className="secondary" onClick={async () => saveBlob(await api.addressSchedule(id, options), `address-schedule-${id}.csv`)}>
              Download the schedule (CSV)
            </button>
            {can("relations.edit") && (
              <button type="button" disabled={data.numbered === 0 || data.truncated} onClick={() => void apply()}>
                Apply to the map
              </button>
            )}
          </div>
          {data.rows.length > 0 && (
            <table className="data" aria-label="Proposed addresses">
              <thead>
                <tr>
                  <th>Street</th>
                  <th>Code</th>
                  <th>Number</th>
                  <th>Property</th>
                  <th>Side</th>
                  <th>From the start</th>
                  <th>Now on the map</th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((row) => (
                  <tr key={row.property}>
                    <td>{row.street_name || <span className="error">No name</span>}</td>
                    <td>{row.street_code}</td>
                    <td>
                      <strong>{row.number}</strong>
                    </td>
                    <td>{row.label}</td>
                    <td>{row.side}</td>
                    <td>{row.distance_m} m</td>
                    <td className={row.current && row.current !== row.number ? "error" : undefined}>{row.current || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {data.numbered > data.rows.length && <p className="muted small">Showing the first {data.rows.length}; the schedule has all {data.numbered}.</p>}
        </>
      )}
    </section>
  );
}
