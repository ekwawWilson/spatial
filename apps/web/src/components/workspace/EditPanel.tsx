import type { Layer } from "@spatial/map-core";

import type { EditMode, EditSettings } from "../map/editing";

const MODES: { mode: EditMode; label: string; lines?: boolean }[] = [
  { mode: "draw", label: "Draw" },
  { mode: "modify", label: "Edit vertices" },
  { mode: "move", label: "Move" },
  { mode: "split", label: "Split", lines: true },
  { mode: "select-many", label: "Select to merge" },
  { mode: "delete", label: "Delete" },
];

export function EditPanel(props: {
  layer: Layer;
  layers: Layer[];
  settings: EditSettings | null;
  available: boolean;
  mergeCount: number;
  undoLabel: string | null;
  redoLabel: string | null;
  busy: boolean;
  onSettings(settings: EditSettings | null): void;
  onUndo(): void;
  onRedo(): void;
  onMerge(): void;
}) {
  const settings = props.settings;
  const base: EditSettings = settings ?? {
    layerId: props.layer.id,
    geometryType: props.layer.geometry_type,
    mode: "draw",
    snapLayerIds: [props.layer.id],
    snapTolerance: 10,
  };
  const set = (change: Partial<EditSettings>) => props.onSettings({ ...base, ...change });

  return (
    <section className="edit-panel" aria-label="Editing">
      <div className="inline-form">
        <strong>Editing {props.layer.name}</strong>
        {MODES.filter((m) => !(m.lines && props.layer.geometry_type === "point")).map((m) => (
          <button
            key={m.mode}
            type="button"
            aria-pressed={settings?.mode === m.mode}
            className={settings?.mode === m.mode ? "" : "secondary"}
            onClick={() => (settings?.mode === m.mode ? props.onSettings(null) : set({ mode: m.mode }))}
          >
            {m.label}
          </button>
        ))}
        {settings?.mode === "select-many" && (
          <button type="button" disabled={props.mergeCount < 2 || props.busy} onClick={props.onMerge}>
            Merge {props.mergeCount} selected
          </button>
        )}
        <button type="button" className="secondary" disabled={!props.undoLabel || props.busy} onClick={props.onUndo} title={props.undoLabel ?? ""}>
          Undo{props.undoLabel ? ` ${props.undoLabel.toLowerCase()}` : ""}
        </button>
        <button type="button" className="secondary" disabled={!props.redoLabel || props.busy} onClick={props.onRedo} title={props.redoLabel ?? ""}>
          Redo{props.redoLabel ? ` ${props.redoLabel.toLowerCase()}` : ""}
        </button>
        {settings && (
          <button type="button" className="link" onClick={() => props.onSettings(null)}>
            Stop editing
          </button>
        )}
      </div>
      {settings && (
        <div className="inline-form small">
          <span>Snap to:</span>
          {props.layers
            .filter((l) => l.feature_count <= 2000)
            .map((l) => (
              <label key={l.id} className="checkbox">
                <input
                  type="checkbox"
                  checked={settings.snapLayerIds.includes(l.id)}
                  onChange={(e) =>
                    set({
                      snapLayerIds: e.target.checked
                        ? [...settings.snapLayerIds, l.id]
                        : settings.snapLayerIds.filter((id) => id !== l.id),
                    })
                  }
                />
                {l.name}
              </label>
            ))}
          <label>
            within
            <input
              type="number"
              min={1}
              max={50}
              value={settings.snapTolerance}
              aria-label="Snapping distance in pixels"
              onChange={(e) => set({ snapTolerance: Math.max(1, Number(e.target.value)) })}
              style={{ width: "4rem" }}
            />
            px
          </label>
          {settings.mode === "split" && <span className="muted">Draw a line across the feature selected on the map.</span>}
          {settings.mode === "select-many" && <span className="muted">Shift-click to select several touching features.</span>}
        </div>
      )}
      {settings && !props.available && (
        <p role="alert" className="error small">
          This layer has too many features to edit on the map. Edit it in a smaller project, or import changes (Phase 5).
        </p>
      )}
    </section>
  );
}
