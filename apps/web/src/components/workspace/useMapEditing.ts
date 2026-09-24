import type { ApiClient, GeoJSONGeometry, Layer, MapFeature } from "@spatial/map-core";
import { useCallback, useMemo, useRef, useState } from "react";

import type { EditCallbacks, EditSettings } from "../map/editing";
import { EditStack, type FeatureState } from "./editStack";

const MAP_CRS = "EPSG:3857";

function stateOf(feature: MapFeature): FeatureState {
  return { geometry: feature.geometry, properties: feature.properties };
}

/** Values for required fields without defaults, asked for when drawing (the
 * server refuses a feature without them). Null if the user cancels. */
function askRequired(layer: Layer): Record<string, unknown> | null {
  const properties: Record<string, unknown> = {};
  for (const field of layer.schema) {
    if (!field.required || field.default !== undefined) continue;
    const value = window.prompt(`${field.label} (required)`);
    if (value === null) return null;
    properties[field.name] = value;
  }
  return properties;
}

/** Map editing for the workspace: turns map gestures into API saves, records
 * them for undo/redo, and reports errors. Coordinates go to the server in
 * EPSG:3857 with geometry_crs, and the server converts them to the layer's CRS. */
export function useMapEditing(options: {
  api: ApiClient;
  layers: Layer[];
  selectedFeature: { layerId: number; featureId: number } | null;
  onChanged(): void;
  onError(error: unknown): void;
}) {
  const { api, layers, onChanged, onError } = options;
  const stack = useRef(new EditStack());
  const [settings, setSettings] = useState<EditSettings | null>(null);
  const [available, setAvailable] = useState(true);
  const [mergeSelection, setMergeSelection] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [, setStackVersion] = useState(0);
  const refresh = () => setStackVersion((v) => v + 1);

  const layer = settings ? (layers.find((l) => l.id === settings.layerId) ?? null) : null;

  const guarded = useCallback(
    async (action: () => Promise<void>) => {
      setBusy(true);
      try {
        await action();
        onChanged();
      } catch (err) {
        onError(err);
        onChanged(); // redraw from the server's state
      } finally {
        setBusy(false);
        refresh();
      }
    },
    [onChanged, onError],
  );

  const callbacks: EditCallbacks = useMemo(
    () => ({
      onDrawn(geometry: GeoJSONGeometry) {
        if (!layer) return;
        const properties = askRequired(layer);
        if (properties === null) return;
        void guarded(async () => {
          const created = await api.createFeature(layer.id, { geometry, geometry_crs: MAP_CRS, properties });
          stack.current.record({ label: "Draw", layerId: layer.id, featureId: created.id, before: null, after: stateOf(created) });
        });
      },
      onReshaped(featureId: number, geometry: GeoJSONGeometry) {
        if (!layer) return;
        void guarded(async () => {
          const before = await api.getFeature(featureId);
          const after = await api.updateFeature(featureId, { version: before.meta.version, geometry, geometry_crs: MAP_CRS });
          stack.current.record({
            label: settings?.mode === "move" ? "Move" : "Edit vertices",
            layerId: layer.id,
            featureId,
            before: stateOf(before),
            after: stateOf(after),
          });
        });
      },
      onDeleteRequested(featureId: number) {
        if (!layer || !window.confirm("Delete this feature? You can undo it, and its history is kept.")) return;
        void guarded(async () => {
          const before = await api.getFeature(featureId);
          await api.deleteFeature(featureId);
          stack.current.record({ label: "Delete", layerId: layer.id, featureId, before: stateOf(before), after: null });
        });
      },
      onSplitLine(line: GeoJSONGeometry) {
        const target = options.selectedFeature;
        if (!layer || !target || target.layerId !== layer.id) {
          onError(new Error("First select the feature to split (Identify, then click it), then draw the line."));
          return;
        }
        void guarded(async () => {
          const before = await api.getFeature(target.featureId);
          const { features } = await api.splitFeature(target.featureId, before.meta.version, line, MAP_CRS);
          const [original, ...created] = features;
          stack.current.record({ label: "Split", layerId: layer.id, featureId: target.featureId, before: stateOf(before), after: stateOf(original!) });
          for (const piece of created) {
            stack.current.record({ label: "Split", layerId: layer.id, featureId: piece.id, before: null, after: stateOf(piece) });
          }
        });
      },
      onSelectMany(ids: number[]) {
        setMergeSelection(ids);
      },
    }),
    [api, guarded, layer, onError, options.selectedFeature, settings?.mode],
  );

  const merge = useCallback(() => {
    if (!layer || mergeSelection.length < 2) return;
    const [keep, ...others] = mergeSelection;
    void guarded(async () => {
      const befores = await Promise.all(mergeSelection.map((id) => api.getFeature(id)));
      const merged = await api.mergeFeatures(mergeSelection, keep!);
      stack.current.record({ label: "Merge", layerId: layer.id, featureId: keep!, before: stateOf(befores[0]!), after: stateOf(merged) });
      others.forEach((id, i) =>
        stack.current.record({ label: "Merge", layerId: layer.id, featureId: id, before: stateOf(befores[i + 1]!), after: null }),
      );
      setMergeSelection([]);
    });
  }, [api, guarded, layer, mergeSelection]);

  const apply = useCallback(
    async (direction: "undo" | "redo") => {
      const step = direction === "undo" ? stack.current.nextUndo() : stack.current.nextRedo();
      if (!step) return;
      await guarded(async () => {
        let recreated: number | undefined;
        if (step.kind === "create") {
          const created = await api.createFeature(step.layerId, {
            geometry: step.state.geometry,
            properties: step.state.properties,
          });
          recreated = created.id;
        } else if (step.kind === "update") {
          const current = await api.getFeature(step.featureId);
          await api.updateFeature(step.featureId, {
            version: current.meta.version,
            geometry: step.state.geometry,
            properties: step.state.properties,
          });
        } else {
          await api.deleteFeature(step.featureId);
        }
        if (direction === "undo") stack.current.undoApplied(recreated);
        else stack.current.redoApplied(recreated);
      });
    },
    [api, guarded],
  );

  return {
    settings,
    setSettings: (next: EditSettings | null) => {
      setSettings(next);
      setMergeSelection([]);
    },
    available,
    setAvailable,
    callbacks,
    mergeSelection,
    merge,
    busy,
    undo: () => apply("undo"),
    redo: () => apply("redo"),
    undoLabel: stack.current.undoLabel,
    redoLabel: stack.current.redoLabel,
  };
}
