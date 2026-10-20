import { ROLE_LABELS } from "@spatial/map-core";
import { Link } from "react-router-dom";

import { Icon, type IconName } from "../components/Icon";
import { useLoad } from "../components/useLoad";
import { useSession } from "../session";

function Stat(props: { to: string; icon: IconName; label: string; value: number | string | undefined; note: string; bad?: boolean }) {
  return (
    <Link to={props.to} className="stat">
      <span className="stat-label">
        <Icon name={props.icon} size={16} />
        {props.label}
      </span>
      <span className={`stat-value${props.bad ? " bad" : ""}`}>{props.value ?? "—"}</span>
      <span className="stat-note">{props.note}</span>
    </Link>
  );
}

function Tile(props: { to: string; icon: IconName; title: string; text: string }) {
  return (
    <Link to={props.to} className="tile">
      <span className="tile-icon">
        <Icon name={props.icon} />
      </span>
      <span>
        <strong>{props.title}</strong>
        <span className="muted">{props.text}</span>
      </span>
    </Link>
  );
}

export function HomePage() {
  const { api, me, districts, districtId, membership, can } = useSession();
  const district = districts.find((d) => d.id === districtId);
  // Figures for the district; a page that can't load one simply shows a dash.
  const projects = useLoad(() => (district && can("project.view") ? api.listProjects() : Promise.resolve(null)), [api, districtId]);
  const duties = useLoad(() => (district && can("reports.view") ? api.compliance() : Promise.resolve(null)), [api, districtId]);
  const d = duties.data;

  return (
    <section className="page">
      <div className="hero-strip">
        <div>
          <h1>Welcome{me?.first_name ? `, ${me.first_name}` : ""}</h1>
          {district ? (
            <p>
              You're working in <strong>{district.name}</strong>
              {membership ? ` as ${ROLE_LABELS[membership.role].toLowerCase()}` : " as system administrator"}.
            </p>
          ) : (
            <p>You don't have access to any district yet. Ask your district administrator to add you.</p>
          )}
        </div>
        {district && can("project.view") && (
          <Link to="/projects" className="tile" style={{ minWidth: "14rem" }}>
            <span className="tile-icon">
              <Icon name="map" />
            </span>
            <span>
              <strong>Open the projects</strong>
              <span className="muted">Maps, plans and permits</span>
            </span>
          </Link>
        )}
      </div>

      {district && (
        <>
          <div className="stat-grid">
            {can("project.view") && <Stat to="/projects" icon="map" label="Plan projects" value={projects.data?.count ?? projects.data?.results.length} note="in this district" />}
            {can("reports.view") && (
              <Stat to="/deadlines" icon="clock" label="Past a statutory date" value={d?.overdue} note="permits, requests, enforcement, zoning" bad={(d?.overdue ?? 0) > 0} />
            )}
            {can("reports.view") && <Stat to="/deadlines" icon="stamp" label="Open permit applications" value={d?.permits.open} note={d ? `${d.permits.received_this_year} received this year` : "this year"} />}
            {can("reports.view") && <Stat to="/deadlines" icon="alert" label="Open enforcement cases" value={d?.enforcement.open} note="notices and their 14-day steps" />}
          </div>

          <h2>Go to</h2>
          <div className="tile-grid">
            {can("project.view") && <Tile to="/projects" icon="map" title="Projects" text="The map workspace, layers, imports and exports" />}
            {can("project.view") && <Tile to="/readiness" icon="check" title="Readiness" text="What each project still needs before planning starts" />}
            {can("reports.view") && <Tile to="/deadlines" icon="clock" title="Statutory deadlines" text="Every clock of L.I. 2384 for the district" />}
            {can("dataroom.view") && <Tile to="/data-room" icon="globe" title="Public Data Room" text="What residents see, and their requests" />}
            <Tile to="/crs" icon="compass" title="Coordinate systems" text="Ghana National Grid, UTM and custom definitions" />
            {can("membership.view") && <Tile to="/members" icon="users" title="Members" text="Who works in this district, and their roles" />}
          </div>
        </>
      )}
    </section>
  );
}
