import {
  describeAccuracy,
  formatPosition,
  parsePositions,
  registerSystems,
  type CoordinateSystem,
  type CrsOperation,
  type DefinitionPreview,
  type Position,
} from "@spatial/map-core";
import { useEffect, useState, type FormEvent } from "react";

import { ErrorMessage } from "../components/ErrorMessage";
import { useLoad } from "../components/useLoad";
import { useSession } from "../session";

const SOURCE_LABELS = { user: "your personal default", district: "the district default", system: "the system default" };

function SystemSelect(props: {
  label: string;
  systems: CoordinateSystem[];
  value: number | null;
  onChange(id: number | null): void;
  emptyLabel?: string;
  disabled?: boolean;
}) {
  return (
    <label>
      {props.label}
      <select
        aria-label={props.label}
        value={props.value ?? ""}
        disabled={props.disabled}
        onChange={(e) => props.onChange(e.target.value ? Number(e.target.value) : null)}
      >
        {props.emptyLabel !== undefined && <option value="">{props.emptyLabel}</option>}
        {props.systems.map((s) => (
          <option key={s.id} value={s.id}>
            {s.code} · {s.name}
          </option>
        ))}
      </select>
    </label>
  );
}

export function CrsPage() {
  const { api, districtId, can, me } = useSession();
  const systems = useLoad(() => api.listCrs(), [api, districtId]);
  const defaults = useLoad(() => api.crsDefaults(), [api, districtId]);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    if (systems.data) registerSystems(systems.data);
  }, [systems.data]);

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

  const all = systems.data ?? [];
  const shared = all.filter((s) => s.scope !== "district");
  const canManage = can("crs.manage");
  const isSysadmin = Boolean(me?.is_system_admin);

  return (
    <section className="page">
      <h1>Coordinate systems</h1>
      <ErrorMessage error={error ?? systems.error ?? defaults.error} />

      {defaults.data && (
        <div className="card wide">
          <h2>Default for new projects</h2>
          <p role="status">
            New projects start in <strong>{defaults.data.effective.crs.code}</strong> ({defaults.data.effective.crs.name}),
            from {SOURCE_LABELS[defaults.data.effective.source]}. Changing a default never changes existing projects.
          </p>
          <div className="inline-form">
            <SystemSelect
              label="Your personal default"
              systems={shared}
              value={defaults.data.user?.id ?? null}
              emptyLabel="Use the district or system default"
              onChange={(id) => run(() => api.setMyDefaultCrs(id), defaults.reload)}
            />
            {districtId && (
              <SystemSelect
                label="District default"
                systems={all}
                value={defaults.data.district?.id ?? null}
                emptyLabel="Use the system default"
                disabled={!canManage}
                onChange={(id) => run(() => api.setDistrictDefaultCrs(id), defaults.reload)}
              />
            )}
            <SystemSelect
              label="System default"
              systems={shared}
              value={defaults.data.system.id}
              disabled={!isSysadmin}
              onChange={(id) => id && run(() => api.setSystemDefaultCrs(id), defaults.reload)}
            />
          </div>
        </div>
      )}

      {all.length > 0 && <Converter systems={all} />}
      {all.length > 0 && <Operations systems={all} canPin={isSysadmin} />}

      <h2>Available systems</h2>
      <table className="data">
        <thead>
          <tr>
            <th>Code</th>
            <th>Name</th>
            <th>Units</th>
            <th>Area of use</th>
            <th>Scope</th>
            <th>Notes</th>
          </tr>
        </thead>
        <tbody>
          {all.map((s) => (
            <tr key={s.id}>
              <td>{s.code}</td>
              <td>{s.name}</td>
              <td>{s.units}</td>
              <td>{s.area_of_use}</td>
              <td>{s.scope === "builtin" ? "Built-in" : s.scope === "global" ? "All districts" : "This district"}</td>
              <td className="muted">{s.notes}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {(canManage || isSysadmin) && (
        <AddSystemForm
          canGlobal={isSysadmin}
          canDistrict={canManage && districtId !== null}
          onAdd={(data) => run(() => api.addCrs(data), systems.reload)}
        />
      )}
    </section>
  );
}

function Converter({ systems }: { systems: CoordinateSystem[] }) {
  const { api } = useSession();
  const [from, setFrom] = useState(systems.find((s) => s.code === "EPSG:4326")?.code ?? systems[0]!.code);
  const [to, setTo] = useState(systems.find((s) => s.code === "EPSG:2136")?.code ?? systems[0]!.code);
  const [text, setText] = useState("");
  const [result, setResult] = useState<{ points: Position[]; operation: CrsOperation } | null>(null);
  const [error, setError] = useState<unknown>(null);
  const target = systems.find((s) => s.code === to);

  async function convert(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setResult(null);
    const { positions, badLines } = parsePositions(text);
    if (badLines.length) {
      setError(new Error(`Can't read line ${badLines.join(", ")}: enter "x y" or "x,y" per line.`));
      return;
    }
    if (!positions.length) return;
    try {
      setResult(await api.transformPoints(from, to, positions));
    } catch (err) {
      setError(err);
    }
  }

  const options = systems.map((s) => (
    <option key={s.code} value={s.code}>
      {s.code} · {s.name}
    </option>
  ));

  return (
    <form className="card wide" onSubmit={convert} aria-label="Convert coordinates">
      <h2>Convert coordinates</h2>
      <div className="inline-form">
        <label>
          From
          <select aria-label="Convert from" value={from} onChange={(e) => setFrom(e.target.value)}>
            {options}
          </select>
        </label>
        <label>
          To
          <select aria-label="Convert to" value={to} onChange={(e) => setTo(e.target.value)}>
            {options}
          </select>
        </label>
      </div>
      <label>
        Coordinates (one point per line: east north, or longitude latitude)
        <textarea rows={4} value={text} onChange={(e) => setText(e.target.value)} />
      </label>
      <ErrorMessage error={error} />
      <button type="submit">Convert</button>
      {result && target && (
        <div role="region" aria-label="Conversion result">
          <p>
            Using <strong>{result.operation.name}</strong> ({describeAccuracy(result.operation.accuracy_m)}
            {result.operation.pinned ? ", chosen by an administrator" : ""}).
          </p>
          <ol>
            {result.points.map((p, i) => (
              <li key={i}>{formatPosition(target, p)}</li>
            ))}
          </ol>
        </div>
      )}
    </form>
  );
}

function Operations({ systems, canPin }: { systems: CoordinateSystem[]; canPin: boolean }) {
  const { api } = useSession();
  const [from, setFrom] = useState(systems.find((s) => s.code === "EPSG:2136")?.code ?? systems[0]!.code);
  const [to, setTo] = useState("EPSG:4326");
  const ops = useLoad(() => api.crsOperations(from, to), [api, from, to]);
  const [error, setError] = useState<unknown>(null);

  async function run(action: () => Promise<void>) {
    setError(null);
    try {
      await action();
      ops.reload();
    } catch (err) {
      setError(err);
    }
  }

  const options = systems.map((s) => (
    <option key={s.code} value={s.code}>
      {s.code}
    </option>
  ));

  return (
    <div className="card wide">
      <h2>Transformation between two systems</h2>
      <p className="muted">
        Converting between datums (for example the Accra datum and WGS 84 used by GPS) is only as accurate as the
        transformation used. The same one is used in both directions, so converting and converting back returns the
        original coordinates.
      </p>
      <div className="inline-form">
        <label>
          From
          <select value={from} onChange={(e) => setFrom(e.target.value)} aria-label="Operation from">
            {options}
          </select>
        </label>
        <label>
          To
          <select value={to} onChange={(e) => setTo(e.target.value)} aria-label="Operation to">
            {options}
          </select>
        </label>
      </div>
      <ErrorMessage error={error ?? ops.error} />
      {ops.data && (
        <table className="data">
          <thead>
            <tr>
              <th>Operation</th>
              <th>Accuracy</th>
              <th aria-label="Status" />
            </tr>
          </thead>
          <tbody>
            {ops.data.candidates.map((op) => {
              const inUse = op.name === ops.data!.current.name;
              return (
                <tr key={op.pipeline}>
                  <td>{op.name}</td>
                  <td>{describeAccuracy(op.accuracy_m)}</td>
                  <td>
                    {inUse ? (
                      <strong>In use{ops.data!.current.pinned ? " (pinned)" : ""}</strong>
                    ) : (
                      canPin && (
                        <button type="button" className="link" onClick={() => run(() => api.pinCrsOperation(from, to, op.pipeline))}>
                          Use this
                        </button>
                      )
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      {canPin && ops.data?.current.pinned && (
        <button type="button" className="link" onClick={() => run(() => api.unpinCrsOperation(from, to))}>
          Go back to the most accurate available
        </button>
      )}
    </div>
  );
}

function AddSystemForm(props: {
  canGlobal: boolean;
  canDistrict: boolean;
  onAdd(data: { name: string; definition: string; notes: string; scope: "district" | "global" }): Promise<boolean>;
}) {
  const { api } = useSession();
  const [name, setName] = useState("");
  const [definition, setDefinition] = useState("");
  const [notes, setNotes] = useState("");
  const [scope, setScope] = useState<"district" | "global">(props.canDistrict ? "district" : "global");
  const [preview, setPreview] = useState<DefinitionPreview | null>(null);
  const [error, setError] = useState<unknown>(null);

  async function check() {
    setError(null);
    setPreview(null);
    try {
      setPreview(await api.validateCrs(definition));
    } catch (err) {
      setError(err);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!(await props.onAdd({ name, definition, notes, scope }))) return;
    setName("");
    setDefinition("");
    setNotes("");
    setPreview(null);
  }

  return (
    <form className="card wide" onSubmit={submit} aria-label="Add coordinate system">
      <h2>Add a coordinate system</h2>
      <p className="muted">
        For a local or project grid that isn't an EPSG system. Paste its WKT or PROJ definition, as supplied by the
        surveyor, and check it before adding.
      </p>
      <label>
        Name
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Kasoa local grid" />
      </label>
      <label>
        Definition (WKT or PROJ string)
        <textarea rows={4} required value={definition} onChange={(e) => setDefinition(e.target.value)} />
      </label>
      <label>
        Notes
        <input value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Source, accuracy, who supplied it" />
      </label>
      {props.canGlobal && props.canDistrict && (
        <label>
          Available to
          <select value={scope} onChange={(e) => setScope(e.target.value as "district" | "global")}>
            <option value="district">This district only</option>
            <option value="global">All districts</option>
          </select>
        </label>
      )}
      <ErrorMessage error={error} />
      {preview && (
        <p role="status">
          {preview.epsg
            ? `This is EPSG:${preview.epsg} (${preview.name}); ask a system administrator to enable it instead.`
            : `${preview.name}: ${preview.kind}, units ${preview.units}${preview.area_of_use ? `, ${preview.area_of_use}` : ""}.`}
        </p>
      )}
      <div className="inline-form">
        <button type="button" onClick={check} disabled={!definition.trim()}>
          Check definition
        </button>
        <button type="submit" disabled={!definition.trim()}>
          Add
        </button>
      </div>
    </form>
  );
}
