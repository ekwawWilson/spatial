import { describe, expect, it } from "vitest";

import { EditStack, type FeatureState } from "./editStack";

const square: FeatureState = { geometry: { type: "Polygon", coordinates: [[[0, 0], [1, 0], [1, 1], [0, 0]]] }, properties: { pid: "A" } };
const moved: FeatureState = { geometry: { type: "Polygon", coordinates: [[[5, 0], [6, 0], [6, 1], [5, 0]]] }, properties: { pid: "A" } };

describe("EditStack", () => {
  it("undoes an update by saving the earlier state, and redoes it", () => {
    const stack = new EditStack();
    stack.record({ label: "Move", layerId: 1, featureId: 7, before: square, after: moved });
    expect(stack.nextUndo()).toEqual({ kind: "update", featureId: 7, state: square });
    stack.undoApplied();
    expect(stack.canUndo).toBe(false);
    expect(stack.nextRedo()).toEqual({ kind: "update", featureId: 7, state: moved });
    stack.redoApplied();
    expect(stack.undoLabel).toBe("Move");
  });

  it("undoing a create deletes; redoing re-creates and remaps the id", () => {
    const stack = new EditStack();
    stack.record({ label: "Draw", layerId: 1, featureId: 7, before: null, after: square });
    stack.record({ label: "Move", layerId: 1, featureId: 7, before: square, after: moved });
    stack.undoApplied(); // undo move
    expect(stack.nextUndo()).toEqual({ kind: "delete", featureId: 7 });
    stack.undoApplied(); // undo draw (deleted)
    expect(stack.nextRedo()).toEqual({ kind: "create", layerId: 1, state: square });
    stack.redoApplied(42); // re-created as feature 42
    expect(stack.nextRedo()).toEqual({ kind: "update", featureId: 42, state: moved });
  });

  it("undoing a delete re-creates the feature", () => {
    const stack = new EditStack();
    stack.record({ label: "Delete", layerId: 3, featureId: 9, before: square, after: null });
    expect(stack.nextUndo()).toEqual({ kind: "create", layerId: 3, state: square });
  });

  it("a new edit clears what could be redone", () => {
    const stack = new EditStack();
    stack.record({ label: "Draw", layerId: 1, featureId: 1, before: null, after: square });
    stack.undoApplied();
    expect(stack.canRedo).toBe(true);
    stack.record({ label: "Draw", layerId: 1, featureId: 2, before: null, after: square });
    expect(stack.canRedo).toBe(false);
  });

  it("keeps a bounded history", () => {
    const stack = new EditStack(2);
    for (const id of [1, 2, 3]) stack.record({ label: `E${id}`, layerId: 1, featureId: id, before: square, after: moved });
    stack.undoApplied();
    stack.undoApplied();
    expect(stack.canUndo).toBe(false);
  });
});
