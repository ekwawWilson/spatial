import type { DistrictKind } from "@spatial/map-core";
import { useState, type FormEvent } from "react";

import { ErrorMessage } from "../components/ErrorMessage";
import { useLoad } from "../components/useLoad";
import { useSession } from "../session";

const KINDS: Record<DistrictKind, string> = {
  metropolitan: "Metropolitan",
  municipal: "Municipal",
  district: "District",
};

export function DistrictsPage() {
  const { api } = useSession();
  const regions = useLoad(() => api.listRegions(), [api]);
  const districts = useLoad(() => api.listDistricts(), [api]);
  const [error, setError] = useState<unknown>(null);

  async function run(action: () => Promise<unknown>, reload: () => void): Promise<boolean> {
    setError(null);
    try {
      await action();
      reload();
      return true;
    } catch (err) {
      setError(err);
      return false;
    }
  }

  return (
    <section className="page">
      <h1>Regions and districts</h1>
      <ErrorMessage error={error ?? regions.error ?? districts.error} />

      <h2>Regions</h2>
      <RegionForm onCreate={(data) => run(() => api.createRegion(data), regions.reload)} />
      <ul>
        {regions.data?.map((r) => (
          <li key={r.id}>
            {r.name} ({r.code})
          </li>
        ))}
      </ul>

      <h2>Districts (MMDAs)</h2>
      {regions.data && regions.data.length > 0 ? (
        <DistrictForm
          regions={regions.data}
          onCreate={(data) => run(() => api.createDistrict(data), districts.reload)}
        />
      ) : (
        <p className="muted">Add a region first.</p>
      )}
      <table className="data">
        <thead>
          <tr>
            <th>Name</th>
            <th>Code</th>
            <th>Type</th>
            <th>Region</th>
            <th>Status</th>
            <th aria-label="Actions" />
          </tr>
        </thead>
        <tbody>
          {districts.data?.map((d) => (
            <tr key={d.id} className={d.is_active ? "" : "inactive"}>
              <td>{d.name}</td>
              <td>{d.code}</td>
              <td>{KINDS[d.kind]}</td>
              <td>{d.region_name}</td>
              <td>{d.is_active ? "Active" : "Deactivated"}</td>
              <td>
                <button
                  type="button"
                  className="link"
                  onClick={() => run(() => api.updateDistrict(d.id, { is_active: !d.is_active }), districts.reload)}
                >
                  {d.is_active ? "Deactivate" : "Reactivate"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function RegionForm({ onCreate }: { onCreate(data: { name: string; code: string }): Promise<boolean> }) {
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!(await onCreate({ name, code }))) return;
    setName("");
    setCode("");
  }
  return (
    <form className="inline-form" onSubmit={submit} aria-label="Add region">
      <input required placeholder="Region name" aria-label="Region name" value={name} onChange={(e) => setName(e.target.value)} />
      <input required placeholder="Code" aria-label="Region code" value={code} onChange={(e) => setCode(e.target.value)} />
      <button type="submit">Add region</button>
    </form>
  );
}

function DistrictForm({
  regions,
  onCreate,
}: {
  regions: { id: number; name: string }[];
  onCreate(data: { name: string; code: string; kind: DistrictKind; region: number }): Promise<boolean>;
}) {
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [kind, setKind] = useState<DistrictKind>("municipal");
  const [region, setRegion] = useState(regions[0]?.id ?? 0);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!(await onCreate({ name, code, kind, region }))) return;
    setName("");
    setCode("");
  }
  return (
    <form className="inline-form" onSubmit={submit} aria-label="Add district">
      <input required placeholder="Assembly name" aria-label="District name" value={name} onChange={(e) => setName(e.target.value)} />
      <input required placeholder="Code" aria-label="District code" value={code} onChange={(e) => setCode(e.target.value)} />
      <select aria-label="Type" value={kind} onChange={(e) => setKind(e.target.value as DistrictKind)}>
        {Object.entries(KINDS).map(([k, label]) => (
          <option key={k} value={k}>
            {label}
          </option>
        ))}
      </select>
      <select aria-label="Region" value={region} onChange={(e) => setRegion(Number(e.target.value))}>
        {regions.map((r) => (
          <option key={r.id} value={r.id}>
            {r.name}
          </option>
        ))}
      </select>
      <button type="submit">Add district</button>
    </form>
  );
}
