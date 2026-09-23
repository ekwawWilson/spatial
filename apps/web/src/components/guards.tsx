import type { Permission } from "@spatial/map-core";
import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { useSession } from "../session";

export function RequireAuth({ children }: { children: ReactNode }) {
  const { me, loading } = useSession();
  const location = useLocation();
  if (loading) return <p className="page">Loading…</p>;
  if (!me) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <>{children}</>;
}

export function Forbidden({ reason }: { reason: string }) {
  return (
    <section className="page">
      <h1>Not available</h1>
      <p role="alert">{reason}</p>
    </section>
  );
}

export function RequirePermission({ permission, children }: { permission: Permission; children: ReactNode }) {
  const { can, districtId, ready } = useSession();
  if (!ready) return <p className="page">Loading…</p>;
  if (!districtId) return <Forbidden reason="Select a district first." />;
  if (!can(permission)) return <Forbidden reason="Your role in this district does not allow this." />;
  return <>{children}</>;
}

export function RequireSystemAdmin({ children }: { children: ReactNode }) {
  const { me } = useSession();
  if (!me?.is_system_admin) return <Forbidden reason="Only system administrators can open this page." />;
  return <>{children}</>;
}
