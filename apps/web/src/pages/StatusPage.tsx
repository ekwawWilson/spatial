import type { HealthReport } from "@spatial/map-core";
import { useEffect, useState } from "react";

import { useSession } from "../session";

type State = { kind: "loading" } | { kind: "loaded"; report: HealthReport } | { kind: "error"; message: string };

/** Service health: confirms the web app, API, database, GDAL and Redis are connected. */
export function StatusPage() {
  const { api } = useSession();
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    api
      .getHealth()
      .then((report) => setState({ kind: "loaded", report }))
      .catch((err: unknown) => setState({ kind: "error", message: err instanceof Error ? err.message : String(err) }));
  }, [api]);

  return (
    <main className="page">
      <h1>Spatial Planning Platform</h1>
      {state.kind === "loading" && <p>Checking services…</p>}
      {state.kind === "error" && <p role="alert">Cannot reach the API: {state.message}</p>}
      {state.kind === "loaded" && <HealthTable report={state.report} />}
    </main>
  );
}

function HealthTable({ report }: { report: HealthReport }) {
  const rows: [string, boolean, string][] = [
    ["Database", report.database.ok, report.database.ok ? `PostGIS ${report.database.postgis}` : (report.database.error ?? "")],
    [
      "GDAL",
      report.gdal.ok,
      report.gdal.ok ? `GDAL ${report.gdal.version}` : `Missing drivers: ${report.gdal.missing_drivers?.join(", ") ?? report.gdal.error}`,
    ],
    ["Redis", report.redis.ok, report.redis.error ?? ""],
  ];
  return (
    <>
      <p role="status">{report.ok ? "All services OK" : "Some services are failing"}</p>
      <table>
        <tbody>
          {rows.map(([name, ok, detail]) => (
            <tr key={name}>
              <th scope="row">{name}</th>
              <td>{ok ? "OK" : "FAIL"}</td>
              <td>{detail}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
