import {
  convert,
  formatArea,
  formatLength,
  formatPosition,
  registerSystems,
  type CoordinateSystem,
  type Layer,
} from "@spatial/map-core";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ErrorMessage } from "../components/ErrorMessage";
import { MapView, type Measurement, type Tool } from "../components/map/MapView";
import { useLoad } from "../components/useLoad";
import { AttributeTable, IdentifyPanel } from "../components/workspace/AttributeTable";
import { SchemaEditor, StyleEditor } from "../components/workspace/LayerEditors";
import { LayerTree } from "../components/workspace/LayerTree";
import { useSession } from "../session";

type Dialog = { kind: "style" | "fields"; layer: Layer } | null;

export function ProjectWorkspace() {
  const { projectId } = useParams();
  const id = Number(projectId);
  const { api, can, districtId } = useSession();
  const project = useLoad(() => api.getProject(id), [api, id, districtId]);
  const layersLoad = useLoad(() => api.listLayers(id), [api, id, districtId]);
  const systems = useLoad(() => api.listCrs(), [api, districtId]);
  const [layers, setLayers] = useState<Layer[]>([]);
  const [selectedLayerId, setSelectedLayerId] = useState<number | null>(null);
  const [selected, setSelected] = useState<{ layerId: number; featureId: number } | null>(null);
  const [tool, setTool] = useState<Tool>("identify");
  const [measurement, setMeasurement] = useState<Measurement | null>(null);
  const [pointer, setPointer] = useState<[number, number] | null>(null);
  const [zoomTo, setZoomTo] = useState<{ extent: number[]; seq: number } | null>(null);
  const [dataVersion, setDataVersion] = useState(0);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [error, setError] = useState<unknown>(null);
  const canEditLayers = can("layer.edit");

  useEffect(() => {
    if (layersLoad.data) setLayers(layersLoad.data);
  }, [layersLoad.data]);
  useEffect(() => {
    if (systems.data) registerSystems(systems.data);
  }, [systems.data]);

  const projectCrs: CoordinateSystem | undefined = useMemo(
    () => systems.data?.find((s) => s.id === project.data?.crs),
    [systems.data, project.data],
  );
  const selectedLayer = layers.find((l) => l.id === selectedLayerId) ?? null;

  const run = useCallback(async (action: () => Promise<unknown>): Promise<boolean> => {
    setError(null);
    try {
      await action();
      return true;
    } catch (err) {
      setError(err);
      return false;
    }
  }, []);

  async function changeLayer(layer: Layer, change: Partial<Layer>) {
    setLayers((all) => all.map((l) => (l.id === layer.id ? { ...l, ...change } : l))); // immediate on the map
    await run(async () => {
      const saved = await api.updateLayer(layer.id, change);
      setLayers((all) => all.map((l) => (l.id === saved.id ? saved : l)));
    });
  }

  async function moveLayer(layerId: number, direction: -1 | 1) {
    const order = layers.map((l) => l.id);
    const i = order.indexOf(layerId);
    const j = i + direction;
    if (j < 0 || j >= order.length) return;
    [order[i], order[j]] = [order[j]!, order[i]!];
    const reordered = order.map((lid, index) => ({ ...layers.find((l) => l.id === lid)!, order: order.length - index }));
    setLayers(reordered);
    await run(() => api.setLayerOrder(id, order));
  }

  async function zoomToLayer(layer: Layer) {
    await run(async () => {
      const extent = await api.layerExtent(layer.id);
      if (extent.wgs84) setZoomTo({ extent: extent.wgs84, seq: Date.now() });
      else setError(new Error(`${layer.name} has no features yet.`));
    });
  }

  const pointerText =
    pointer && projectCrs
      ? (() => {
          try {
            return formatPosition(projectCrs, convert("EPSG:3857", projectCrs.code, pointer));
          } catch {
            return "";
          }
        })()
      : "";

  if (project.error) return <ErrorMessage error={project.error} />;

  return (
    <div className="workspace">
      <header className="workspace-header">
        <Link to="/projects">Projects</Link>
        <h1>{project.data?.name ?? "…"}</h1>
        <span className="muted">
          {project.data?.community} · {project.data?.crs_detail.code} {project.data?.crs_detail.name}
        </span>
        <span className="spacer" />
        <div className="tools" role="toolbar" aria-label="Map tools">
          {(
            [
              ["identify", "Identify"],
              ["measure-length", "Measure distance"],
              ["measure-area", "Measure area"],
            ] as [Tool, string][]
          ).map(([value, label]) => (
            <button key={value} type="button" aria-pressed={tool === value} className={tool === value ? "" : "secondary"} onClick={() => setTool(value)}>
              {label}
            </button>
          ))}
        </div>
      </header>
      <ErrorMessage error={error ?? layersLoad.error} />
      <aside className="workspace-side">
        <LayerTree
          layers={layers}
          selectedLayerId={selectedLayerId}
          canEdit={canEditLayers}
          onSelect={setSelectedLayerId}
          onChange={changeLayer}
          onMove={moveLayer}
          onZoom={zoomToLayer}
          onEditStyle={(layer) => setDialog({ kind: "style", layer })}
          onEditFields={(layer) => setDialog({ kind: "fields", layer })}
          onDelete={(layer) =>
            window.confirm(`Delete layer "${layer.name}" and its ${layer.feature_count} features?`) &&
            run(async () => {
              await api.deleteLayer(layer.id);
              setLayers((all) => all.filter((l) => l.id !== layer.id));
            })
          }
          onAdd={(data) =>
            run(async () => {
              const layer = await api.createLayer({ ...data, project: id });
              setLayers((all) => [layer, ...all]);
              setSelectedLayerId(layer.id);
            })
          }
        />
      </aside>
      <main className="workspace-map">
        <MapView
          api={api}
          layers={layers}
          dataVersion={dataVersion}
          selected={selected}
          tool={tool}
          onSelect={(hit) => {
            setSelected(hit);
            if (hit) setSelectedLayerId(hit.layerId);
          }}
          onMeasure={setMeasurement}
          onPointer={setPointer}
          zoomTo={zoomTo}
        />
        <div className="map-status" aria-live="polite">
          <span aria-label="Pointer position">{pointerText}</span>
          {measurement && (
            <span role="status">
              {measurement.kind === "length"
                ? formatLength(measurement.value, projectCrs)
                : formatArea(measurement.value)}
            </span>
          )}
        </div>
        {selected && layers.find((l) => l.id === selected.layerId) && (
          <IdentifyPanel
            layer={layers.find((l) => l.id === selected.layerId)!}
            featureId={selected.featureId}
            onClose={() => setSelected(null)}
          />
        )}
      </main>
      <section className="workspace-table">
        {selectedLayer ? (
          <AttributeTable
            layer={selectedLayer}
            canEdit={can("feature.edit")}
            selectedFeatureId={selected?.layerId === selectedLayer.id ? selected.featureId : null}
            dataVersion={dataVersion}
            onSelect={(featureId) => setSelected({ layerId: selectedLayer.id, featureId })}
            onSaved={() => setDataVersion((v) => v + 1)}
          />
        ) : (
          <p className="muted">Select a layer to see its attribute table.</p>
        )}
      </section>
      {dialog?.kind === "style" && (
        <div className="dialog" role="dialog" aria-modal="true" aria-label="Edit style">
          <StyleEditor
            layer={dialog.layer}
            onClose={() => setDialog(null)}
            onSave={(style) => run(async () => {
              const saved = await api.updateLayer(dialog.layer.id, { style });
              setLayers((all) => all.map((l) => (l.id === saved.id ? saved : l)));
            })}
          />
        </div>
      )}
      {dialog?.kind === "fields" && (
        <div className="dialog" role="dialog" aria-modal="true" aria-label="Edit fields">
          <SchemaEditor
            layer={dialog.layer}
            onClose={() => setDialog(null)}
            onSave={async (schema, confirmDrop) => {
              try {
                const saved = await api.updateLayer(dialog.layer.id, { schema }, confirmDrop);
                setLayers((all) => all.map((l) => (l.id === saved.id ? saved : l)));
                setDataVersion((v) => v + 1);
                return true;
              } catch (err) {
                return err;
              }
            }}
          />
        </div>
      )}
    </div>
  );
}
