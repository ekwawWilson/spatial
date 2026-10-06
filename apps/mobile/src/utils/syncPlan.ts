// What to send to the server, and what each reply means for the device.
// Pure decisions, so they can be tested without a phone or a server.

import type { LocalFeature, LocalTask, SyncChange, SyncResult } from "../types";

/** The changes to push: new captures, edits to server features, finished
 * tasks. Features waiting on a conflict are not sent again. */
export function buildChanges(features: LocalFeature[], tasks: LocalTask[]): SyncChange[] {
  const changes: SyncChange[] = [];
  for (const feature of features) {
    if (!feature.changeId || (feature.state !== "new" && feature.state !== "edited")) continue;
    const capture = {
      method: feature.method,
      accuracy_m: feature.accuracyM,
      fix_time: feature.fixTime,
      readings: feature.readings,
      captured_at: feature.capturedAt,
      notes: feature.notes,
    };
    if (feature.state === "new") {
      changes.push({
        change_id: feature.changeId,
        op: "create",
        layer: feature.layerId,
        feature_uuid: feature.uuid,
        geometry: feature.geometry,
        properties: feature.properties,
        capture,
      });
    } else {
      changes.push({
        change_id: feature.changeId,
        op: "update",
        feature_uuid: feature.uuid,
        base_version: feature.version,
        properties: feature.properties,
        capture,
      });
    }
  }
  // Tasks go last, so a correction arrives before the task that reports it.
  for (const task of tasks) {
    if (!task.pending || !task.changeId || !task.outcome) continue;
    changes.push({ change_id: task.changeId, op: "task", task: { id: task.id, outcome: task.outcome, notes: task.notes } });
  }
  return changes;
}

export type FeatureAction =
  /** The server has it: the device's copy now matches version `version`. */
  | { kind: "synced"; uuid: string; serverId: number; version: number }
  /** The server already had this capture, but not these latest values: send them as an edit next time. */
  | { kind: "resend-as-edit"; uuid: string; serverId: number; version: number }
  | { kind: "conflict"; uuid: string }
  | { kind: "rejected"; uuid: string; message: string };

export type TaskAction = { kind: "sent"; id: number } | { kind: "rejected"; id: number; message: string };

/** What to do on the device for one reply. `repeat` means the server had
 * already applied exactly this change (the first reply was lost). */
export function featureAction(feature: LocalFeature, result: SyncResult): FeatureAction {
  if (result.status === "conflict") return { kind: "conflict", uuid: feature.uuid };
  if (result.status === "rejected" || !result.feature) {
    return { kind: "rejected", uuid: feature.uuid, message: (result.errors ?? ["The server refused this change."]).join(" ") };
  }
  const { id, version } = result.feature;
  // "duplicate" without "repeat": an older send of this capture got through,
  // and the feature has been saved again on the device since.
  if (result.duplicate && !result.repeat) return { kind: "resend-as-edit", uuid: feature.uuid, serverId: id, version };
  return { kind: "synced", uuid: feature.uuid, serverId: id, version };
}

export function taskAction(task: LocalTask, result: SyncResult): TaskAction {
  if (result.status === "applied") return { kind: "sent", id: task.id };
  return { kind: "rejected", id: task.id, message: (result.errors ?? ["The server refused this result."]).join(" ") };
}

/** The byte ranges still to upload for a photo, from where the server has got to. */
export function chunkRanges(size: number, received: number, chunkSize: number): [number, number][] {
  const ranges: [number, number][] = [];
  for (let start = Math.max(0, received); start < size; start += chunkSize) {
    ranges.push([start, Math.min(size, start + chunkSize)]);
  }
  return ranges;
}

/** May the server's copy replace the device's? Never when the device holds
 * something that hasn't been sent. A conflict is the office's to settle, so
 * its answer replaces the device's copy. */
export function serverMayReplace(local: LocalFeature | undefined): boolean {
  return !local || local.state === "synced" || local.state === "conflict";
}

export interface SyncSummary {
  sent: number;
  conflicts: number;
  rejected: number;
  photos: number;
  photosWaiting: number;
  received: number;
  removed: number;
  tasks: number;
}

export function describe(summary: SyncSummary): string {
  const parts: string[] = [];
  parts.push(summary.sent ? `${summary.sent} sent` : "nothing to send");
  if (summary.photos) parts.push(`${summary.photos} photo(s) uploaded`);
  if (summary.photosWaiting) parts.push(`${summary.photosWaiting} photo(s) still to upload`);
  if (summary.conflicts) parts.push(`${summary.conflicts} waiting for the office to settle a conflict`);
  if (summary.rejected) parts.push(`${summary.rejected} refused (open them to see why)`);
  parts.push(`${summary.received} update(s) from the office`);
  if (summary.removed) parts.push(`${summary.removed} removed`);
  if (summary.tasks) parts.push(`${summary.tasks} feature(s) to check`);
  return parts.join(" · ");
}
