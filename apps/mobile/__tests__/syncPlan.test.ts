import type { LocalFeature, LocalTask } from "../src/types";
import { buildChanges, chunkRanges, describe as describeSync, featureAction, serverMayReplace, taskAction } from "../src/utils/syncPlan";

function feature(extra: Partial<LocalFeature> = {}): LocalFeature {
  return {
    localId: 1,
    uuid: "f-1",
    serverId: null,
    layerId: 7,
    projectId: 3,
    geometry: { type: "Point", coordinates: [-0.2, 5.6] },
    properties: { pid: "A" },
    version: 0,
    verified: false,
    state: "new",
    capturedAt: "2026-10-06T09:00:05Z",
    capturedBy: "kofi@example.test",
    method: "gps",
    accuracyM: 3.2,
    fixTime: "2026-10-06T09:00:00Z",
    readings: 5,
    notes: "gate",
    changeId: "c-1",
    syncError: null,
    ...extra,
  };
}

function task(extra: Partial<LocalTask> = {}): LocalTask {
  return { id: 9, projectId: 3, featureUuid: "f-2", layerId: 7, item: "Buildings", status: "done", outcome: "confirmed", notes: "seen", pending: true, changeId: "t-1", ...extra };
}

describe("what the device sends", () => {
  it("sends new captures whole, with how they were recorded", () => {
    expect(buildChanges([feature()], [])).toEqual([
      {
        change_id: "c-1",
        op: "create",
        layer: 7,
        feature_uuid: "f-1",
        geometry: { type: "Point", coordinates: [-0.2, 5.6] },
        properties: { pid: "A" },
        capture: { method: "gps", accuracy_m: 3.2, fix_time: "2026-10-06T09:00:00Z", readings: 5, captured_at: "2026-10-06T09:00:05Z", notes: "gate" },
      },
    ]);
  });

  it("sends edits with the version they were based on, and no geometry", () => {
    const [change] = buildChanges([feature({ state: "edited", version: 4, serverId: 55 })], []);
    expect(change).toMatchObject({ op: "update", base_version: 4, feature_uuid: "f-1" });
    expect(change).not.toHaveProperty("geometry");
  });

  it("leaves out what is already in step or waiting on a conflict, and puts tasks last", () => {
    const changes = buildChanges(
      [feature({ uuid: "a", state: "synced" }), feature({ uuid: "b", state: "conflict" }), feature({ uuid: "c", state: "edited", changeId: "c-3" })],
      [task(), task({ id: 10, pending: false }), task({ id: 11, outcome: "", changeId: "t-3" })],
    );
    expect(changes.map((c) => c.op)).toEqual(["update", "task"]);
    expect(changes[1]).toEqual({ change_id: "t-1", op: "task", task: { id: 9, outcome: "confirmed", notes: "seen" } });
  });
});

describe("what a reply means", () => {
  const applied = { change_id: "c-1", status: "applied" as const, feature: { id: 55, uuid: "f-1", version: 1 } };

  it("marks an applied change as in step, with the server's id and version", () => {
    expect(featureAction(feature(), applied)).toEqual({ kind: "synced", uuid: "f-1", serverId: 55, version: 1 });
  });

  it("treats a repeated reply the same as the first (the first was lost)", () => {
    expect(featureAction(feature(), { ...applied, repeat: true }).kind).toBe("synced");
    expect(featureAction(feature(), { ...applied, repeat: true, duplicate: true }).kind).toBe("synced");
  });

  it("re-sends as an edit when the server has an older send of the same capture", () => {
    expect(featureAction(feature(), { ...applied, duplicate: true })).toEqual({ kind: "resend-as-edit", uuid: "f-1", serverId: 55, version: 1 });
  });

  it("keeps conflicts and refusals on the device", () => {
    expect(featureAction(feature({ state: "edited" }), { change_id: "c-1", status: "conflict", conflict: 4 })).toEqual({ kind: "conflict", uuid: "f-1" });
    expect(featureAction(feature(), { change_id: "c-1", status: "rejected", errors: ["use: is required"] })).toEqual({
      kind: "rejected",
      uuid: "f-1",
      message: "use: is required",
    });
  });

  it("closes a task only when the server accepted it", () => {
    expect(taskAction(task(), { change_id: "t-1", status: "applied", task: 9 })).toEqual({ kind: "sent", id: 9 });
    expect(taskAction(task(), { change_id: "t-1", status: "rejected", errors: ["gone"] })).toEqual({ kind: "rejected", id: 9, message: "gone" });
  });
});

describe("photo uploads", () => {
  it("splits a photo into chunks", () => {
    expect(chunkRanges(10, 0, 4)).toEqual([[0, 4], [4, 8], [8, 10]]);
  });

  it("resumes from where the server has got to", () => {
    expect(chunkRanges(10, 4, 4)).toEqual([[4, 8], [8, 10]]);
    expect(chunkRanges(10, 10, 4)).toEqual([]);
  });
});

describe("updates from the office", () => {
  it("never replaces something that hasn't been sent", () => {
    expect(serverMayReplace(undefined)).toBe(true);
    expect(serverMayReplace(feature({ state: "synced" }))).toBe(true);
    expect(serverMayReplace(feature({ state: "conflict" }))).toBe(true); // the office decided
    expect(serverMayReplace(feature({ state: "new" }))).toBe(false);
    expect(serverMayReplace(feature({ state: "edited" }))).toBe(false);
  });

  it("summarises a sync in plain words", () => {
    expect(describeSync({ sent: 3, conflicts: 1, rejected: 0, photos: 2, photosWaiting: 1, received: 5, removed: 0, tasks: 4 })).toBe(
      "3 sent · 2 photo(s) uploaded · 1 photo(s) still to upload · 1 waiting for the office to settle a conflict · 5 update(s) from the office · 4 feature(s) to check",
    );
    expect(describeSync({ sent: 0, conflicts: 0, rejected: 0, photos: 0, photosWaiting: 0, received: 0, removed: 0, tasks: 0 })).toBe(
      "nothing to send · 0 update(s) from the office",
    );
  });
});
