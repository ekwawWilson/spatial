import {
  ApiError,
  convert,
  formatArea,
  formatLength,
  formatPosition,
  registerSystems,
  type BasemapConfig,
  type BoundaryReport,
  type CoordinateSystem,
  type Layer,
} from "@spatial/map-core";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";

import { ErrorMessage } from "../components/ErrorMessage";
import { MapView, type Measurement, type Tool } from "../components/map/MapView";
import { useLoad } from "../components/useLoad";
import { AttributeTable, IdentifyPanel } from "../components/workspace/AttributeTable";
import { BasemapPicker } from "../components/workspace/BasemapPicker";
import { BoundaryPanel } from "../components/workspace/BoundaryPanel";
import { EditPanel } from "../components/workspace/EditPanel";
import { ExportDialog } from "../components/workspace/ExportDialog";
import { ImportWizard, type ImportBinding } from "../components/workspace/ImportWizard";
import { SchemaEditor, StyleEditor } from "../components/workspace/LayerEditors";
import { LayerTree } from "../components/workspace/LayerTree";
import { useMapEditing } from "../components/workspace/useMapEditing";
import { useSession } from "../session";

type Dialog =
  | { kind: "style" | "fields"; layer: Layer }
  | { kind: "import"; binding?: ImportBinding }
  | { kind: "export"; layerIds?: number[] }
  | null;

/** What the checklist page asks the workspace to open (router state). */
export type ChecklistAction =
  | { kind: "import"; binding: ImportBinding }
  | { kind: "export"; layerId: number }
  | { kind: "draw"; layerId: number };

export function ProjectWorkspace() {
  const { projectId } = useParams();
  const id = Number(projectId);
  const { api, can, districtId } = useSession();
  const location = useLocation();
  const navigate = useNavigate();
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
  const basemaps = useLoad(() => api.listBasemaps(), [api, districtId]);
  const basemapKey = `spatial.basemap.${id}`;
  const [basemapId, setBasemapId] = useState<number | null | undefined>(() => {
    try {
      const stored = localStorage.getItem(basemapKey);
      return stored === null ? undefined : stored === "" ? null : Number(stored);
    } catch {
      return undefined;
    }
  });
  const [basemapConfig, setBasemapConfig] = useState<BasemapConfig | null>(null);
  const [basemapOpacity, setBasemapOpacity] = useState(1);
  const [basemapProblem, setBasemapProblem] = useState<string | null>(null);

  // Default to the first available basemap until the user picks one.
  const effectiveBasemapId = basemapId === undefined ? (basemaps.data?.[0]?.id ?? null) : basemapId;

  useEffect(() => {
    setBasemapConfig(null);
    setBasemapProblem(null);
    if (effectiveBasemapId === null) return;
    let current = true;
    api
      .basemapConfig(effectiveBasemapId)
      .then((config) => current && setBasemapConfig(config))
      .catch((err: unknown) => {
        if (!current) return;
        const detail = err instanceof ApiError ? err.message : String(err);
        setBasemapProblem(detail);
      });
    return () => {
      current = false;
    };
  }, [api, effectiveBasemapId]);

  const boundaryLoad = useLoad(() => api.boundaryReport(id), [api, id, districtId]);
  const [boundary, setBoundary] = useState<BoundaryReport | null>(null);
  const [drawingBoundary, setDrawingBoundary] = useState(false);
  useEffect(() => {
    if (boundaryLoad.data) setBoundary(boundaryLoad.data);
  }, [boundaryLoad.data]);

  const editing = useMapEditing({
    api,
    layers,
    selectedFeature: selected,
    onChanged: () => {
      setDataVersion((v) => v + 1);
      layersLoad.reload();
    },
    onError: setError,
  });

  // Open the tool a checklist item asked for, once the layers are loaded.
  const checklistAction = (location.state as { checklist?: ChecklistAction } | null)?.checklist;
  useEffect(() => {
    if (!checklistAction || !layersLoad.data) return;
    navigate(location.pathname, { replace: true, state: null });
    if (checklistAction.kind === "import") {
      setDialog({ kind: "import", binding: checklistAction.binding });
    } else if (checklistAction.kind === "export") {
      setDialog({ kind: "export", layerIds: [checklistAction.layerId] });
    } else {
      const layer = layersLoad.data.find((l) => l.id === checklistAction.layerId);
      if (!layer) return;
      setSelectedLayerId(layer.id);
      setTool("identify");
      editing.setSettings({
        layerId: layer.id,
        geometryType: layer.geometry_type,
        mode: "draw",
        snapLayerIds: [layer.id],
        snapTolerance: 10,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [checklistAction, layersLoad.data]);

  function chooseBasemap(value: number | null) {
    setBasemapId(value);
    try {
      localStorage.setItem(basemapKey, value === null ? "" : String(value));
    } catch {
      // storage unavailable: choice lasts for this visit
    }
  }

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
        <Link to={`/projects/${id}/checklist`}>Readiness checklist</Link>
        {can("data.import") && (
          <button type="button" className="secondary" onClick={() => setDialog({ kind: "import" })}>
            Import data
          </button>
        )}
        {can("data.export") && (
          <button type="button" className="secondary" onClick={() => setDialog({ kind: "export" })} disabled={layers.length === 0}>
            Export
          </button>
        )}
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
        {project.data && (
          <BoundaryPanel
            project={project.data}
            report={boundary}
            systems={systems.data ?? []}
            drawing={drawingBoundary}
            onDraw={() => {
              editing.setSettings(null);
              setDrawingBoundary(!drawingBoundary);
            }}
            onChanged={(report) => {
              setBoundary(report);
              layersLoad.reload();
              setDataVersion((v) => v + 1);
            }}
          />
        )}
        <BasemapPicker
          basemaps={basemaps.data ?? []}
          selectedId={effectiveBasemapId}
          opacity={basemapOpacity}
          problem={basemapProblem}
          onSelect={chooseBasemap}
          onOpacity={setBasemapOpacity}
        />
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
          basemap={basemapConfig}
          basemapOpacity={basemapOpacity}
          onBasemapError={setBasemapProblem}
          edit={editing.settings}
          editCallbacks={editing.callbacks}
          onEditAvailability={editing.setAvailable}
          onBoundaryDrawn={
            drawingBoundary
              ? (geometry) => {
                  setDrawingBoundary(false);
                  void run(async () => {
                    setBoundary(await api.setBoundary(id, geometry, "drawn", "EPSG:3857"));
                    layersLoad.reload();
                    setDataVersion((v) => v + 1);
                  });
                }
              : null
          }
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
            canEdit={can("feature.edit")}
            onClose={() => setSelected(null)}
            onRestored={() => {
              setDataVersion((v) => v + 1);
              boundaryLoad.reload();
            }}
          />
        )}
      </main>
      <section className="workspace-table">
        {selectedLayer && can("feature.edit") && (
          <EditPanel
            layer={selectedLayer}
            layers={layers}
            settings={editing.settings?.layerId === selectedLayer.id ? editing.settings : null}
            available={editing.available}
            mergeCount={editing.mergeSelection.length}
            undoLabel={editing.undoLabel}
            redoLabel={editing.redoLabel}
            busy={editing.busy}
            onSettings={(next) => {
              editing.setSettings(next);
              if (next) {
                setTool("identify");
                setDrawingBoundary(false);
              }
            }}
            onUndo={editing.undo}
            onRedo={editing.redo}
            onMerge={editing.merge}
          />
        )}
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
      {dialog?.kind === "import" && (
        <div className="dialog">
          <ImportWizard
            projectId={id}
            layers={layers}
            systems={systems.data ?? []}
            binding={dialog.binding}
            onDone={() => {
              layersLoad.reload();
              setDataVersion((v) => v + 1);
            }}
            onClose={() => setDialog(null)}
          />
        </div>
      )}
      {dialog?.kind === "export" && (
        <div className="dialog">
          <ExportDialog
            projectId={id}
            layers={layers}
            systems={systems.data ?? []}
            selection={selected ? { layerId: selected.layerId, featureIds: [selected.featureId] } : null}
            initialLayerIds={dialog.layerIds}
            onClose={() => setDialog(null)}
          />
        </div>
      )}
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
