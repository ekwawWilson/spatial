import type { AddressingMethod, AddressingOptions, MapFeature, StreetName } from "@spatial/map-core";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";

import { ErrorMessage } from "../components/ErrorMessage";
import { useLoad } from "../components/useLoad";
import { saveBlob } from "../components/workspace/ExportDialog";
import { useSession } from "../session";

const NEXT: Record<StreetName["status"], string> = {
  proposed: "Consult the community",
  consulted: "For the Spatial Planning Committee",
  approved: "Approved",
  refused: "Refused",
};

/** Street names from proposal to signs: consulted, approved by the Committee, written to the map, published, signed (r.28). */
function StreetNames({ projectId }: { projectId: number }) {
  const { api, can, districtId } = useSession();
  const list = useLoad(() => api.listStreetNames(projectId), [api, projectId, districtId]);
  const streets = useLoad(async () => {
    const roles = await api.getLayerRoles(projectId);
    const role = roles.roles.find((r) => r.role === "streets" && r.layer !== null);
    if (!role || role.layer === null) return null;
    const field = String(role.config.name_field ?? "name");
    const page = await api.listFeatures(role.layer, { limit: 2000 });
    return page.features.map((f: MapFeature) => ({ id: f.id, name: String(f.properties[field] ?? "") }));
  }, [api, projectId, districtId]);
  const [items, setItems] = useState<StreetName[]>([]);
  const [values, setValues] = useState({ street: "", name: "", basis: "", proposed_by: "" });
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [error, setError] = useState<unknown>(null);
  const [note, setNote] = useState<string | null>(null);
  useEffect(() => setItems(list.data?.results ?? []), [list.data]);

  const act = async (action: () => Promise<StreetName>, done: string) => {
    setError(null);
    setNote(null);
    try {
      const next = await action();
      setItems(items.map((i) => (i.id === next.id ? next : i)));
      setNote(done);
      return next;
    } catch (err) {
      setError(err);
      return null;
    }
  };

  async function propose(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setNote(null);
    try {
      const made = await api.proposeStreetName({ project: projectId, street: Number(values.street), name: values.name, basis: values.basis, proposed_by: values.proposed_by });
      setItems([made, ...items]);
      setValues({ street: "", name: "", basis: "", proposed_by: "" });
      setNote(made.clashes?.length ? `Proposed. Note: ${made.name} is ${made.clashes.join("; ")}.` : "Proposed. Next: consult the community.");
    } catch (err) {
      setError(err);
    }
  }

  return (
    <section aria-label="Street names" className="card wide">
      <h2>Street names</h2>
      <p className="muted small">
        A name is proposed, the community consulted, then the Spatial Planning Committee approves it (it appears on the Committee's agenda). On
        approval it is written to the street on the map; then record when it was published and when the signs went up. Names must be unique in
        the district. (L.I. 2384 r.28 applies the National Street Naming and Property Numbering Operational Manual.)
      </p>
      <ErrorMessage error={error ?? list.error} />
      {note && <p role="status">{note}</p>}
      {items.length > 0 && (
        <table className="data" aria-label="Names">
          <thead>
            <tr>
              <th>Name</th>
              <th>Street now</th>
              <th>Where it is</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td>
                  <strong>{item.name}</strong>
                  {item.basis && <div className="muted small">{item.basis}</div>}
                </td>
                <td className="small">{item.previous_name || streets.data?.find((s) => s.id === item.street)?.name || "—"}</td>
                <td className="small">
                  <span className={`pill ${item.status === "approved" ? "ok" : item.status === "refused" ? "bad" : "warn"}`}>{NEXT[item.status]}</span>
                  <div className="muted">
                    Proposed {item.proposed_on}
                    {item.consulted_on && `; consulted ${item.consulted_on}`}
                    {item.decided_on && `; decided ${item.decided_on}`}
                    {item.published_on && `; published ${item.published_on}`}
                    {item.signs_on && `; signs ${item.signs_on}`}
                  </div>
                </td>
                <td className="actions">
                  {item.status === "proposed" && can("relations.edit") && (
                    <span className="inline-form">
                      <input aria-label={`Consultation on ${item.name}`} placeholder="Where and with whom" value={notes[item.id] ?? ""} onChange={(e) => setNotes({ ...notes, [item.id]: e.target.value })} />
                      <button type="button" className="secondary" onClick={() => void act(() => api.consultStreetName(item.id, notes[item.id] ?? ""), "Consultation recorded.")}>
                        Consulted
                      </button>
                    </span>
                  )}
                  {item.status === "consulted" && can("permit.decide") && (
                    <span className="inline-form">
                      <button type="button" onClick={() => void act(() => api.decideStreetName(item.id, true), `${item.name} approved and written to the map.`)}>
                        Approve
                      </button>
                      <button type="button" className="danger" onClick={() => void act(() => api.decideStreetName(item.id, false), "Refused.")}>
                        Refuse
                      </button>
                    </span>
                  )}
                  {item.status === "approved" && can("relations.edit") && (
                    <span className="inline-form">
                      {!item.published_on && (
                        <button type="button" className="link" onClick={() => void act(() => api.markStreetName(item.id, "published"), "Publication recorded.")}>
                          Published today
                        </button>
                      )}
                      {!item.signs_on && (
                        <button type="button" className="link" onClick={() => void act(() => api.markStreetName(item.id, "signs"), "Signs recorded.")}>
                          Signs up today
                        </button>
                      )}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {can("relations.edit") && (
        <form className="stack" aria-label="Propose a street name" onSubmit={propose}>
          <h3>Propose a name</h3>
          {streets.data === null && !streets.loading && <p className="muted small">Say which layer holds the streets first (Relationships, Layers).</p>}
          <div className="inline-form">
            <label>
              Street
              <select required aria-label="Street" value={values.street} onChange={(e) => setValues({ ...values, street: e.target.value })}>
                <option value="">Choose…</option>
                {streets.data?.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name || `Unnamed street #${s.id}`}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Proposed name
              <input required aria-label="Proposed name" value={values.name} onChange={(e) => setValues({ ...values, name: e.target.value })} />
            </label>
            <label>
              Proposed by
              <input aria-label="Proposed by" value={values.proposed_by} onChange={(e) => setValues({ ...values, proposed_by: e.target.value })} />
            </label>
          </div>
          <label>
            Why this name
            <input aria-label="Why this name" placeholder="A person, an event, a landmark, a local name" value={values.basis} onChange={(e) => setValues({ ...values, basis: e.target.value })} />
          </label>
          <div className="inline-form">
            <button type="submit">Propose</button>
          </div>
        </form>
      )}
    </section>
  );
}

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
      <StreetNames projectId={id} />
    </section>
  );
}
