import { ROLE_LABELS } from "@spatial/map-core";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { useSession } from "../session";

export function Layout() {
  const { me, districts, districtId, setDistrictId, membership, can, signOut } = useSession();
  const navigate = useNavigate();

  async function handleSignOut() {
    await signOut();
    navigate("/login");
  }

  return (
    <div className="shell">
      <header className="topbar">
        <span className="brand">Spatial Planning Platform</span>
        {districts.length > 0 ? (
          <label className="district-switcher">
            <span>District</span>
            <select value={districtId ?? ""} onChange={(e) => setDistrictId(Number(e.target.value))}>
              {districts.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <span className="muted">No district access yet</span>
        )}
        <span className="role">
          {me?.is_system_admin ? "System administrator" : membership ? ROLE_LABELS[membership.role] : ""}
        </span>
        <span className="spacer" />
        <NavLink to="/account">{me?.email}</NavLink>
        <button type="button" className="link" onClick={handleSignOut}>
          Sign out
        </button>
      </header>
      <nav className="sidebar" aria-label="Main">
        <NavLink to="/" end>
          Home
        </NavLink>
        {can("project.view") && <NavLink to="/projects">Projects</NavLink>}
        <NavLink to="/crs">Coordinate systems</NavLink>
        {can("membership.view") && <NavLink to="/members">Members</NavLink>}
        {can("audit.view") && <NavLink to="/audit">Audit log</NavLink>}
        {me?.is_system_admin && (
          <>
            <span className="nav-heading">System</span>
            <NavLink to="/admin/districts">Regions &amp; districts</NavLink>
            <NavLink to="/admin/users">Users</NavLink>
          </>
        )}
      </nav>
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
