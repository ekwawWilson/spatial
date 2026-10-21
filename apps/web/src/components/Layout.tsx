import { ROLE_LABELS } from "@spatial/map-core";
import { useState, type ReactNode } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { useSession } from "../session";
import { Icon, Logo, type IconName } from "./Icon";
import { QuickSearch } from "./QuickSearch";

const COLLAPSED_KEY = "spatial.nav.collapsed";

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}

function Item({ to, icon, end, children }: { to: string; icon: IconName; end?: boolean; children: ReactNode }) {
  return (
    <NavLink to={to} end={end} className="nav-item">
      <Icon name={icon} />
      <span className="nav-label">{children}</span>
    </NavLink>
  );
}

function initials(first: string | undefined, last: string | undefined, email: string | undefined): string {
  const letters = `${first?.[0] ?? ""}${last?.[0] ?? ""}`.trim();
  return (letters || email?.[0] || "?").toUpperCase();
}

export function Layout() {
  const { me, districts, districtId, setDistrictId, membership, can, signOut } = useSession();
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useState(readCollapsed);

  function toggle() {
    const next = !collapsed;
    setCollapsed(next);
    try {
      localStorage.setItem(COLLAPSED_KEY, next ? "1" : "0");
    } catch {
      // A private window: the choice lasts until the page is reloaded.
    }
  }

  async function handleSignOut() {
    await signOut();
    navigate("/login");
  }

  const role = me?.is_system_admin ? "System administrator" : membership ? ROLE_LABELS[membership.role] : "";

  return (
    <div className={`shell${collapsed ? " nav-collapsed" : ""}`}>
      <header className="topbar">
        <button type="button" className="icon-button topbar-toggle" onClick={toggle} aria-label={collapsed ? "Show the menu" : "Hide the menu"} title={collapsed ? "Show the menu" : "Hide the menu"}>
          <Icon name="menu" />
        </button>
        <NavLink to="/" className="brand" aria-label="Spatial Planning Platform: home">
          <Logo />
          <span className="brand-text">
            <span className="brand-name">Spatial Planning Platform</span>
            <span className="brand-sub">Land use and spatial planning</span>
          </span>
        </NavLink>
        {districts.length > 0 ? (
          <label className="district-switcher">
            <Icon name="building" size={16} />
            <span className="visually-hidden">District</span>
            <select aria-label="District" value={districtId ?? ""} onChange={(e) => setDistrictId(Number(e.target.value))}>
              {districts.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <span className="topbar-note">No district access yet</span>
        )}
        {districtId !== null && <QuickSearch />}
        <span className="spacer" />
        <NavLink to="/account" className="user-chip" title="Your account">
          <span className="avatar" aria-hidden="true">
            {initials(me?.first_name, me?.last_name, me?.email)}
          </span>
          <span className="user-text">
            <span className="user-email">{me?.email}</span>
            {role && <span className="role">{role}</span>}
          </span>
        </NavLink>
        <button type="button" className="icon-button" onClick={handleSignOut} title="Sign out">
          <Icon name="logout" />
          <span className="visually-hidden">Sign out</span>
        </button>
      </header>
      <nav className="sidebar" aria-label="Main">
        <span className="nav-heading">Workspace</span>
        <Item to="/" end icon="home">
          Home
        </Item>
        {can("project.view") && (
          <Item to="/projects" icon="map">
            Projects
          </Item>
        )}
        {can("project.view") && (
          <Item to="/readiness" icon="check">
            Readiness
          </Item>
        )}
        {can("reports.view") && (
          <Item to="/deadlines" icon="clock">
            Statutory deadlines
          </Item>
        )}
        {can("permit.view") && (
          <Item to="/committees" icon="users">
            Committees
          </Item>
        )}
        {can("reports.view") && (
          <Item to="/returns" icon="file">
            Returns and data exchange
          </Item>
        )}
        {can("dataroom.view") && (
          <Item to="/data-room" icon="globe">
            Public Data Room
          </Item>
        )}
        <span className="nav-heading">Settings</span>
        <Item to="/crs" icon="compass">
          Coordinate systems
        </Item>
        {(can("basemap.manage") || me?.is_system_admin) && (
          <Item to="/basemaps" icon="layers">
            Basemaps
          </Item>
        )}
        {can("membership.view") && (
          <Item to="/members" icon="users">
            Members
          </Item>
        )}
        {can("audit.view") && (
          <Item to="/audit" icon="list">
            Audit log
          </Item>
        )}
        {me?.is_system_admin && (
          <>
            <span className="nav-heading">System</span>
            <Item to="/admin/districts" icon="grid">
              Regions &amp; districts
            </Item>
            <Item to="/admin/users" icon="shield">
              Users
            </Item>
          </>
        )}
        <span className="spacer" />
        <button type="button" className="nav-collapse" onClick={toggle} aria-label={collapsed ? "Expand the menu" : "Collapse the menu"}>
          <Icon name={collapsed ? "chevronRight" : "chevronLeft"} />
          <span className="nav-label">Collapse</span>
        </button>
      </nav>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
