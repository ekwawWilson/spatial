import type { DataJob, GeoJSONGeometry } from "@spatial/map-core";
import { useEffect, useState, type FormEvent } from "react";

import { useSession } from "../../session";
import { ErrorMessage } from "../ErrorMessage";
import { Icon } from "../Icon";

/** What can be brought in, as transfer/osm.py names it. */
export const OSM_KINDS: [string, string][] = [
  ["streets", "Streets and roads"],
  ["buildings", "Buildings"],
  ["waterways", "Rivers, streams and drains"],
  ["landuse", "Land use, parks and open spaces"],
  ["places", "Schools, clinics, markets and other places"],
];
const LABEL = Object.fromEntries(OSM_KINDS);
const POLL_MS = 2000;

type AreaChoice = "boundary" | "view" | "drawn";

export interface OsmPanelProps {
  projectId: number;
  hasBoundary: boolean;
  /** What's on screen now, in Web Mercator (minx, miny, maxx, maxy). */
  view: [number, number, number, number] | null;
  /** An area drawn on the map for this, in Web Mercator. */
  drawn: GeoJSONGeometry | null;
  drawing: boolean;
  onDraw(): void;
  /** The job finished: the layers it filled. */
  onDone(layerIds: number[]): void;
}

function viewPolygon([minx, miny, maxx, maxy]: [number, number, number, number]): GeoJSONGeometry {
  return { type: "Polygon", coordinates: [[[minx, miny], [maxx, miny], [maxx, maxy], [minx, maxy], [minx, miny]]] } as GeoJSONGeometry;
}

/** Brings the streets, buildings and other features OpenStreetMap has inside an area into the project. */
export function OsmPanel(props: OsmPanelProps) {
  const { api } = useSession();
  const [choice, setChoice] = useState<AreaChoice>(props.hasBoundary ? "boundary" : "view");
  const [kinds, setKinds] = useState<string[]>(["streets", "buildings"]);
  const [job, setJob] = useState<DataJob | null>(null);
  const [error, setError] = useState<unknown>(null);
  const running = job !== null && (job.status === "queued" || job.status === "running");

  useEffect(() => {
    if (props.hasBoundary && choice === "view" && job === null) setChoice("boundary");
    // Only when the planning area first appears.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.hasBoundary]);

  // Follow the job until it ends.
  useEffect(() => {
    if (!running || job === null) return;
    const timer = window.setTimeout(async () => {
      try {
        const next = await api.getJob(job.id);
        setJob(next);
        if (next.status === "done") {
          const layers = (next.report.osm as { layers?: Record<string, number> } | undefined)?.layers ?? {};
          props.onDone(Object.values(layers));
        }
      } catch (err) {
        setError(err);
        setJob(null);
      }
    }, POLL_MS);
    return () => window.clearTimeout(timer);
  }, [api, job, running, props]);

  async function start(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const area =
        choice === "boundary"
          ? { use_boundary: true }
          : choice === "view"
            ? { area: viewPolygon(props.view!), area_crs: "EPSG:3857" }
            : { area: props.drawn!, area_crs: "EPSG:3857" };
      setJob(await api.openStreetMap({ project: props.projectId, kinds, ...area }));
    } catch (err) {
      setError(err);
    }
  }

  const found = (job?.report.osm as { found?: Record<string, number>; already_in_project?: Record<string, number> } | undefined) ?? null;
  const ready = kinds.length > 0 && (choice === "boundary" ? props.hasBoundary : choice === "view" ? props.view !== null : props.drawn !== null);

  return (
    <form className="osm-panel" aria-label="Features from the map" onSubmit={start}>
      <h2>
        <Icon name="layers" size={15} /> Features from the map
      </h2>
      <p className="muted small">Bring in what OpenStreetMap shows inside an area, as layers you can edit, correct and name.</p>
      <fieldset>
        <legend>Area</legend>
        <label className="checkbox">
          <input type="radio" name="osm-area" checked={choice === "boundary"} disabled={!props.hasBoundary} onChange={() => setChoice("boundary")} />
          The planning area{!props.hasBoundary && <span className="muted small"> (none yet)</span>}
        </label>
        <label className="checkbox">
          <input type="radio" name="osm-area" checked={choice === "view"} onChange={() => setChoice("view")} />
          What's on screen now
        </label>
        <label className="checkbox">
          <input type="radio" name="osm-area" checked={choice === "drawn"} onChange={() => setChoice("drawn")} />
          An area I draw on the map
        </label>
        {choice === "drawn" && (
          <div className="inline-form">
            <button type="button" className="secondary" aria-pressed={props.drawing} onClick={props.onDraw}>
              <Icon name="area" size={15} />
              {props.drawing ? "Drawing… (double-click to finish)" : props.drawn ? "Draw it again" : "Draw the area"}
            </button>
            {props.drawn && !props.drawing && <span className="pill ok">Area drawn</span>}
          </div>
        )}
      </fieldset>
      <fieldset>
        <legend>Bring in</legend>
        {OSM_KINDS.map(([code, label]) => (
          <label key={code} className="checkbox">
            <input
              type="checkbox"
              checked={kinds.includes(code)}
              onChange={(e) => setKinds(e.target.checked ? [...kinds, code] : kinds.filter((k) => k !== code))}
            />
            {label}
          </label>
        ))}
      </fieldset>
      <ErrorMessage error={error} />
      <button type="submit" disabled={!ready || running}>
        <Icon name="download" size={15} />
        {running ? "Bringing in…" : "Bring in features"}
      </button>
      {running && (
        <p role="status" className="small">
          {job?.live_progress?.stage ?? "Waiting to start"}. OpenStreetMap can take a minute.
        </p>
      )}
      {job?.status === "failed" && (
        <p role="alert" className="error small">
          {job.error}
        </p>
      )}
      {job?.status === "done" && found?.found && (
        <div role="status" className="small osm-result">
          <strong>Brought in:</strong>
          <ul>
            {Object.entries(found.found).map(([code, count]) => (
              <li key={code}>
                {LABEL[code] ?? code}: {count} new
                {found.already_in_project?.[code] ? `, ${found.already_in_project[code]} already in the project` : ""}
              </li>
            ))}
          </ul>
          Each is in its own layer, "(OpenStreetMap)". Select one to edit its lines and shapes, or name them in its table.
        </div>
      )}
      <p className="muted small">© OpenStreetMap contributors. Check it on the ground before relying on it.</p>
    </form>
  );
}
