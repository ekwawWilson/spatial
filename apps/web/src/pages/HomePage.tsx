import { ROLE_LABELS } from "@spatial/map-core";

import { useSession } from "../session";

export function HomePage() {
  const { me, districts, districtId, membership } = useSession();
  const district = districts.find((d) => d.id === districtId);

  return (
    <section className="page">
      <h1>Welcome{me?.first_name ? `, ${me.first_name}` : ""}</h1>
      {district ? (
        <p>
          You're working in <strong>{district.name}</strong>
          {membership ? ` as ${ROLE_LABELS[membership.role].toLowerCase()}` : " as system administrator"}.
        </p>
      ) : (
        <p>You don't have access to any district yet. Ask your district administrator to add you.</p>
      )}
      <p className="muted">Plan projects and the map workspace arrive in the next phases.</p>
    </section>
  );
}
