// Undo/redo for map edits within a session. Each entry records a feature's
// state before and after one edit (native geometry and properties), so undoing
// and redoing are ordinary saves through the API: nothing is lost from the
// feature's history, which records every step.

import type { GeoJSONGeometry } from "@spatial/map-core";

export interface FeatureState {
  geometry: GeoJSONGeometry | null;
  properties: Record<string, unknown>;
}

export interface Edit {
  label: string;
  layerId: number;
  featureId: number;
  /** null: the feature didn't exist before (a create). */
  before: FeatureState | null;
  /** null: the feature doesn't exist after (a delete). */
  after: FeatureState | null;
}

/** What to do to apply an edit in one direction. */
export type Step =
  | { kind: "create"; layerId: number; state: FeatureState }
  | { kind: "update"; featureId: number; state: FeatureState }
  | { kind: "delete"; featureId: number };

function step(layerId: number, featureId: number, from: FeatureState | null, to: FeatureState | null): Step {
  if (from === null && to !== null) return { kind: "create", layerId, state: to };
  if (to === null) return { kind: "delete", featureId };
  return { kind: "update", featureId, state: to };
}

export class EditStack {
  private done: Edit[] = [];
  private undone: Edit[] = [];

  constructor(private readonly limit = 100) {}

  get canUndo(): boolean {
    return this.done.length > 0;
  }

  get canRedo(): boolean {
    return this.undone.length > 0;
  }

  get undoLabel(): string | null {
    return this.done.at(-1)?.label ?? null;
  }

  get redoLabel(): string | null {
    return this.undone.at(-1)?.label ?? null;
  }

  record(edit: Edit): void {
    this.done.push(edit);
    if (this.done.length > this.limit) this.done.shift();
    this.undone = [];
  }

  /** The step that undoes the last edit (the caller applies it, then calls
   * `undoApplied` with the id of any feature it had to re-create). */
  nextUndo(): Step | null {
    const edit = this.done.at(-1);
    return edit ? step(edit.layerId, edit.featureId, edit.after, edit.before) : null;
  }

  undoApplied(recreatedId?: number): void {
    const edit = this.done.pop();
    if (!edit) return;
    this.undone.push(recreatedId ? this.remap(edit, recreatedId) : edit);
  }

  nextRedo(): Step | null {
    const edit = this.undone.at(-1);
    return edit ? step(edit.layerId, edit.featureId, edit.before, edit.after) : null;
  }

  redoApplied(recreatedId?: number): void {
    const edit = this.undone.pop();
    if (!edit) return;
    this.done.push(recreatedId ? this.remap(edit, recreatedId) : edit);
  }

  /** A re-created feature has a new id: point every entry for it at the new one. */
  private remap(edit: Edit, newId: number): Edit {
    const oldId = edit.featureId;
    for (const list of [this.done, this.undone]) {
      for (const e of list) if (e.featureId === oldId) e.featureId = newId;
    }
    return { ...edit, featureId: newId };
  }
}
