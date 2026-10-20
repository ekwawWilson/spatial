import { Link, Outlet } from "react-router-dom";

import { Logo } from "./Icon";

/** The frame of the pages anyone can open without signing in. */
export function PublicFrame() {
  return (
    <div className="public-frame">
      <header className="public-bar">
        <Link to="/public" className="brand">
          <Logo />
          <span className="brand-text">
            <span className="brand-name">Public Data Room</span>
            <span className="brand-sub">Spatial Planning Platform</span>
          </span>
        </Link>
        <span className="spacer" />
        <Link to="/login" className="public-signin">
          Staff sign in
        </Link>
      </header>
      <div className="public-body">
        <Outlet />
      </div>
      <footer className="public-foot">Land Use and Spatial Planning Act, 2016 (Act 925) · Land Use and Spatial Planning Regulations, 2019 (L.I. 2384)</footer>
    </div>
  );
}
