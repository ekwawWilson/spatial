import type { Basemap, BasemapKind, BasemapPreset } from "@spatial/map-core";
import { useState, type FormEvent } from "react";

import { ErrorMessage } from "../components/ErrorMessage";
import { useLoad } from "../components/useLoad";
import { useSession } from "../session";

const PRESETS: { value: BasemapPreset; label: string; needsKey: boolean }[] = [
  { value: "osm", label: "OpenStreetMap", needsKey: false },
  { value: "esri_imagery", label: "Esri World Imagery", needsKey: false },
  { value: "google_roadmap", label: "Google Maps (roadmap)", needsKey: true },
  { value: "google_satellite", label: "Google Maps (satellite)", needsKey: true },
  { value: "bing_aerial", label: "Bing Maps aerial (deprecated)", needsKey: true },
];

export function BasemapsPage() {
  const { api, districtId, me, can } = useSession();
  const basemaps = useLoad(() => api.listBasemaps({ include_inactive: true }), [api, districtId]);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState("");
  const isSysadmin = Boolean(me?.is_system_admin);
  const canDistrict = can("basemap.manage") && districtId !== null;

  async function run(action: () => Promise<unknown>, message = ""): Promise<boolean> {
    setError(null);
    setNotice("");
    try {
      await action();
      setNotice(message);
      basemaps.reload();
      return true;
    } catch (err) {
      setError(err);
      return false;
    }
  }

  const canEdit = (b: Basemap) => (b.scope === "global" ? isSysadmin : canDistrict);

  return (
    <section className="page">
      <h1>Basemaps</h1>
      <p className="muted">
        Background maps for project maps. Providers' terms apply: OpenStreetMap, Esri, Google and Bing tiles may not be
        stored for offline field use. Only your own or licensed imagery can be marked as allowed offline.
      </p>
      <ErrorMessage error={error ?? basemaps.error} />
      {notice && <p role="status">{notice}</p>}
      <table className="data">
        <thead>
          <tr>
            <th>Name</th>
            <th>Type</th>
            <th>Available to</th>
            <th>API key</th>
            <th>Offline use</th>
            <th>Status</th>
            <th aria-label="Actions" />
          </tr>
        </thead>
        <tbody>
          {basemaps.data?.map((b) => (
            <tr key={b.id} className={b.is_active ? "" : "inactive"}>
              <td title={b.notes}>{b.name}</td>
              <td>{b.kind}</td>
              <td>{b.scope === "global" ? "All districts" : "This district"}</td>
              <td>{b.requires_key ? (b.has_key ? "Set" : "Missing") : "Not needed"}</td>
              <td>{b.offline_cache_allowed ? "Allowed" : "Not allowed"}</td>
              <td>{b.is_active ? "Active" : "Off"}</td>
              <td className="actions">
                {canEdit(b) && (
                  <>
                    {(b.requires_key || b.has_key) && (
                      <button
                        type="button"
                        className="link"
                        onClick={() => {
                          const key = window.prompt(`API key for ${b.name} (leave empty to remove it)`);
                          if (key !== null) void run(() => api.updateBasemap(b.id, { api_key: key.trim() }), `Key for ${b.name} saved.`);
                        }}
                      >
                        {b.has_key ? "Replace key" : "Add key"}
                      </button>
                    )}
                    <button type="button" className="link" onClick={() => run(() => api.updateBasemap(b.id, { is_active: !b.is_active }))}>
                      {b.is_active ? "Turn off" : "Turn on"}
                    </button>
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {(canDistrict || isSysadmin) && (
        <>
          <PresetForm canGlobal={isSysadmin} canDistrict={canDistrict} onAdd={(p, key, scope) => run(() => api.addBasemapPreset(p, key, scope), "Basemap added.")} />
          <CustomForm
            canGlobal={isSysadmin}
            canDistrict={canDistrict}
            onAdd={(data) => run(() => api.createBasemap(data), "Basemap added.")}
          />
        </>
      )}
    </section>
  );
}

function ScopeSelect(props: { canGlobal: boolean; canDistrict: boolean; value: "district" | "global"; onChange(v: "district" | "global"): void }) {
  if (!(props.canGlobal && props.canDistrict)) return null;
  return (
    <label>
      Available to
      <select value={props.value} onChange={(e) => props.onChange(e.target.value as "district" | "global")}>
        <option value="district">This district</option>
        <option value="global">All districts</option>
      </select>
    </label>
  );
}

function PresetForm(props: {
  canGlobal: boolean;
  canDistrict: boolean;
  onAdd(preset: BasemapPreset, key: string, scope: "district" | "global"): Promise<boolean>;
}) {
  const [preset, setPreset] = useState<BasemapPreset>("google_satellite");
  const [key, setKey] = useState("");
  const [scope, setScope] = useState<"district" | "global">(props.canDistrict ? "district" : "global");
  const needsKey = PRESETS.find((p) => p.value === preset)?.needsKey;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (await props.onAdd(preset, key, scope)) setKey("");
  }

  return (
    <form className="card wide" onSubmit={submit} aria-label="Add a ready-made basemap">
      <h2>Add a ready-made basemap</h2>
      <div className="inline-form">
        <select aria-label="Provider" value={preset} onChange={(e) => setPreset(e.target.value as BasemapPreset)}>
          {PRESETS.map((p) => (
            <option key={p.value} value={p.value}>
              {p.label}
            </option>
          ))}
        </select>
        {needsKey && (
          <input aria-label="API key" placeholder="API key" value={key} onChange={(e) => setKey(e.target.value)} autoComplete="off" />
        )}
        <ScopeSelect {...props} value={scope} onChange={setScope} />
        <button type="submit">Add</button>
      </div>
      {preset.startsWith("google") && (
        <p className="muted small">
          Create the key in Google Cloud with the Map Tiles API enabled, and restrict it to this site's address: the key is
          visible to browsers that load the map.
        </p>
      )}
    </form>
  );
}

function CustomForm(props: {
  canGlobal: boolean;
  canDistrict: boolean;
  onAdd(data: Partial<Basemap> & { api_key?: string; scope?: "district" | "global" }): Promise<boolean>;
}) {
  const [name, setName] = useState("");
  const [kind, setKind] = useState<BasemapKind>("xyz");
  const [url, setUrl] = useState("");
  const [layers, setLayers] = useState("");
  const [attribution, setAttribution] = useState("");
  const [offline, setOffline] = useState(false);
  const [scope, setScope] = useState<"district" | "global">(props.canDistrict ? "district" : "global");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (await props.onAdd({ name, kind, url, layers, attribution, offline_cache_allowed: offline, scope })) {
      setName("");
      setUrl("");
      setLayers("");
      setAttribution("");
      setOffline(false);
    }
  }

  return (
    <form className="card wide" onSubmit={submit} aria-label="Add your own basemap">
      <h2>Add your own basemap</h2>
      <p className="muted small">
        For example the district's own imagery server. XYZ URLs need {"{z}"}, {"{x}"} and {"{y}"}; WMS needs the service URL
        and layer names; WMTS needs the capabilities URL and a layer id.
      </p>
      <div className="inline-form">
        <input required aria-label="Basemap name" placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} />
        <select aria-label="Service type" value={kind} onChange={(e) => setKind(e.target.value as BasemapKind)}>
          <option value="xyz">XYZ tiles</option>
          <option value="wms">WMS</option>
          <option value="wmts">WMTS</option>
        </select>
      </div>
      <input required aria-label="Service URL" placeholder="https://…" value={url} onChange={(e) => setUrl(e.target.value)} />
      {kind !== "xyz" && <input aria-label="Layers" placeholder="Layer name(s)" value={layers} onChange={(e) => setLayers(e.target.value)} />}
      <input aria-label="Attribution" placeholder="Attribution (shown on the map)" value={attribution} onChange={(e) => setAttribution(e.target.value)} />
      <label className="checkbox">
        <input type="checkbox" checked={offline} onChange={(e) => setOffline(e.target.checked)} />
        We own this imagery or its licence allows offline use (tiles may be stored on field devices)
      </label>
      <ScopeSelect {...props} value={scope} onChange={setScope} />
      <button type="submit">Add basemap</button>
    </form>
  );
}
