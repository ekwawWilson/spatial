import {
  parsePositions,
  type BoundaryReport,
  type CoordinateSystem,
  type Project,
  type TraverseLeg,
  type TraverseResult,
} from "@spatial/map-core";
import { useState, type FormEvent } from "react";

import { useSession } from "../../session";
import { ErrorMessage } from "../ErrorMessage";

const STATUS_LABELS = { draft: "Draft", agreed: "Agreed with stakeholders", approved: "Approved" };

function fmt(n: number | null | undefined, digits = 2): string {
  return n === null || n === undefined ? "—" : n.toLocaleString("en-GB", { maximumFractionDigits: digits });
}

export function BoundaryPanel(props: {
  project: Project;
  report: BoundaryReport | null;
  systems: CoordinateSystem[];
  drawing: boolean;
  onDraw(): void;
  onChanged(report: BoundaryReport): void;
}) {
  const { api, can } = useSession();
  const [dialog, setDialog] = useState<"coordinates" | "traverse" | null>(null);
  const [error, setError] = useState<unknown>(null);
  const report = props.report;
  const status = report?.status ?? "draft";
  const editable = can("project.edit") && status === "draft";

  async function setStatus(target: "draft" | "agreed" | "approved") {
    setError(null);
    try {
      props.onChanged(await api.setBoundaryStatus(props.project.id, target));
    } catch (err) {
      setError(err);
    }
  }

  return (
    <section className="boundary-panel" aria-label="Planning area">
      <h2>Planning area</h2>
      {!report?.exists ? (
        <p className="muted">No boundary yet.</p>
      ) : (
        <>
          <p>
            <strong>{STATUS_LABELS[status]}</strong>
            {report.valid ? "" : ` · invalid: ${report.invalid_reason}`}
          </p>
          <dl className="facts">
            <dt>Area</dt>
            <dd>
              {fmt(report.area_ha, 4)} ha · {fmt(report.area_acres, 4)} acres · {fmt(report.area_m2, 0)} m²
            </dd>
            <dt>Perimeter</dt>
            <dd>
              {fmt(report.perimeter_m)} m
              {report.perimeter_native ? ` · ${fmt(report.perimeter_native)} ${report.native_units}` : ""}
            </dd>
            <dt>Neighbours</dt>
            <dd>
              {report.neighbours?.length
                ? report.neighbours.map((n) => (
                    <div key={n.project} className={n.kind === "overlap" ? "error" : ""}>
                      {n.kind === "overlap"
                        ? `Overlaps ${n.name} by ${fmt(n.area_m2, 1)} m²`
                        : `Gap of ${fmt(n.distance_m, 2)} m to ${n.name}`}
                    </div>
                  ))
                : "No overlaps or gaps with neighbouring planning areas"}
            </dd>
            <dt>District</dt>
            <dd>
              {!report.district_boundary_loaded
                ? "District boundary not loaded"
                : report.outside_district_m2 && report.outside_district_m2 > 0.01
                  ? `${fmt(report.outside_district_m2, 1)} m² outside the district`
                  : "Inside the district"}
            </dd>
          </dl>
        </>
      )}
      <ErrorMessage error={error} />
      {editable && (
        <div className="inline-form">
          <button type="button" className={props.drawing ? "" : "secondary"} aria-pressed={props.drawing} onClick={props.onDraw}>
            {report?.exists ? "Redraw" : "Draw"}
          </button>
          <button type="button" className="secondary" onClick={() => setDialog("coordinates")}>
            Enter coordinates
          </button>
          <button type="button" className="secondary" onClick={() => setDialog("traverse")}>
            Bearings and distances
          </button>
        </div>
      )}
      {report?.exists && (
        <div className="inline-form">
          {status === "draft" && can("project.edit") && (
            <button type="button" onClick={() => setStatus("agreed")} disabled={!report.valid}>
              Mark as agreed
            </button>
          )}
          {status === "agreed" && can("boundary.approve") && (
            <button type="button" onClick={() => setStatus("approved")}>
              Approve
            </button>
          )}
          {status === "agreed" && can("project.edit") && (
            <button type="button" className="link" onClick={() => setStatus("draft")}>
              Back to draft
            </button>
          )}
          {status === "approved" && can("boundary.approve") && (
            <button type="button" className="link" onClick={() => setStatus("draft")}>
              Reopen
            </button>
          )}
        </div>
      )}
      {dialog === "coordinates" && (
        <div className="dialog">
          <CoordinatesDialog
            project={props.project}
            systems={props.systems}
            onClose={() => setDialog(null)}
            onSaved={(r) => {
              props.onChanged(r);
              setDialog(null);
            }}
          />
        </div>
      )}
      {dialog === "traverse" && (
        <div className="dialog">
          <TraverseDialog
            project={props.project}
            onClose={() => setDialog(null)}
            onSaved={(r) => {
              props.onChanged(r);
              setDialog(null);
            }}
          />
        </div>
      )}
    </section>
  );
}

function CoordinatesDialog(props: {
  project: Project;
  systems: CoordinateSystem[];
  onClose(): void;
  onSaved(report: BoundaryReport): void;
}) {
  const { api } = useSession();
  const [crs, setCrs] = useState(props.project.crs_detail.code);
  const [text, setText] = useState("");
  const [error, setError] = useState<unknown>(null);

  async function save(event: FormEvent) {
    event.preventDefault();
    setError(null);
    const { positions, badLines } = parsePositions(text);
    if (badLines.length) {
      setError(new Error(`Can't read line ${badLines.join(", ")}: enter "x y" or "x,y" per line.`));
      return;
    }
    if (positions.length < 3) {
      setError(new Error("A boundary needs at least three corners."));
      return;
    }
    const ring = [...positions];
    const [first, last] = [ring[0]!, ring[ring.length - 1]!];
    if (first[0] !== last[0] || first[1] !== last[1]) ring.push(first);
    try {
      props.onSaved(await api.setBoundary(props.project.id, { type: "Polygon", coordinates: [ring] }, "coordinates", crs));
    } catch (err) {
      setError(err);
    }
  }

  return (
    <form className="card wide" role="dialog" aria-modal="true" aria-label="Enter boundary coordinates" onSubmit={save}>
      <h2>Enter boundary coordinates</h2>
      <label>
        Coordinates are in
        <select aria-label="Coordinates are in" value={crs} onChange={(e) => setCrs(e.target.value)}>
          {props.systems.map((s) => (
            <option key={s.code} value={s.code}>
              {s.code} · {s.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Corners in order, one per line (east north). You can paste from a spreadsheet.
        <textarea rows={8} aria-label="Corner coordinates" value={text} onChange={(e) => setText(e.target.value)} />
      </label>
      {crs !== props.project.crs_detail.code && (
        <p className="muted small">They'll be converted to the project's {props.project.crs_detail.code}.</p>
      )}
      <ErrorMessage error={error} />
      <div className="inline-form">
        <button type="submit">Use as boundary</button>
        <button type="button" className="link" onClick={props.onClose}>
          Cancel
        </button>
      </div>
    </form>
  );
}

function TraverseDialog(props: { project: Project; onClose(): void; onSaved(report: BoundaryReport): void }) {
  const { api } = useSession();
  const [start, setStart] = useState({ e: "", n: "" });
  const [legs, setLegs] = useState<{ bearing: string; distance: string }[]>([
    { bearing: "", distance: "" },
    { bearing: "", distance: "" },
    { bearing: "", distance: "" },
  ]);
  const [adjust, setAdjust] = useState(true);
  const [scale, setScale] = useState("1");
  const [result, setResult] = useState<TraverseResult | null>(null);
  const [error, setError] = useState<unknown>(null);
  const units = props.project.crs_detail.units;

  function request() {
    return {
      start: [Number(start.e), Number(start.n)] as [number, number],
      legs: legs.filter((l) => l.bearing.trim() || l.distance.trim()).map((l): TraverseLeg => ({ bearing: l.bearing, distance: Number(l.distance) })),
      adjust,
      scale_factor: Number(scale) || 1,
    };
  }

  async function compute(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setResult(null);
    try {
      setResult(await api.computeTraverse(request()));
    } catch (err) {
      setError(err);
    }
  }

  async function use() {
    if (!result) return;
    try {
      props.onSaved(await api.setBoundary(props.project.id, result.polygon, "traverse"));
    } catch (err) {
      setError(err);
    }
  }

  return (
    <form className="card wide" role="dialog" aria-modal="true" aria-label="Boundary from bearings and distances" onSubmit={compute}>
      <h2>Bearings and distances</h2>
      <p className="muted small">
        Grid bearings as 123.5, 123 30 00 or N 56 30 E. Distances in {units}. The last leg should return to the start.
      </p>
      <div className="inline-form">
        <label>
          Start easting
          <input aria-label="Start easting" value={start.e} onChange={(e) => setStart({ ...start, e: e.target.value })} />
        </label>
        <label>
          Start northing
          <input aria-label="Start northing" value={start.n} onChange={(e) => setStart({ ...start, n: e.target.value })} />
        </label>
      </div>
      <table className="data">
        <thead>
          <tr>
            <th>Leg</th>
            <th>Bearing</th>
            <th>Distance ({units})</th>
          </tr>
        </thead>
        <tbody>
          {legs.map((leg, i) => (
            <tr key={i}>
              <td>{i + 1}</td>
              <td>
                <input aria-label={`Leg ${i + 1} bearing`} value={leg.bearing} onChange={(e) => setLegs(legs.map((l, j) => (j === i ? { ...l, bearing: e.target.value } : l)))} />
              </td>
              <td>
                <input aria-label={`Leg ${i + 1} distance`} value={leg.distance} onChange={(e) => setLegs(legs.map((l, j) => (j === i ? { ...l, distance: e.target.value } : l)))} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <button type="button" className="link" onClick={() => setLegs([...legs, { bearing: "", distance: "" }])}>
        Add leg
      </button>
      <div className="inline-form">
        <label className="checkbox">
          <input type="checkbox" checked={adjust} onChange={(e) => setAdjust(e.target.checked)} /> Adjust (Bowditch)
        </label>
        <label>
          Scale factor (ground to grid)
          <input aria-label="Scale factor" value={scale} onChange={(e) => setScale(e.target.value)} style={{ width: "6rem" }} />
        </label>
      </div>
      <ErrorMessage error={error} />
      {result && (
        <div role="region" aria-label="Traverse result">
          <p>
            Misclosure {fmt(result.misclosure, 3)} {units} (E {fmt(result.misclosure_e, 3)}, N {fmt(result.misclosure_n, 3)}) over{" "}
            {fmt(result.perimeter, 2)} {units}:{" "}
            <strong>{result.accuracy_ratio ? `1 in ${Math.round(result.accuracy_ratio).toLocaleString("en-GB")}` : "closes exactly"}</strong>
            {result.adjusted ? "; adjusted with the Bowditch rule." : "."}
          </p>
          {result.accuracy_ratio !== null && result.accuracy_ratio < 5000 && (
            <p className="error small">That's a large misclosure for a boundary. Check the bearings and distances.</p>
          )}
        </div>
      )}
      <div className="inline-form">
        <button type="submit">Compute</button>
        <button type="button" disabled={!result} onClick={use}>
          Use as boundary
        </button>
        <button type="button" className="link" onClick={props.onClose}>
          Cancel
        </button>
      </div>
    </form>
  );
}
