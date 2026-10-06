// Sync one project with the server: send what was captured here, upload
// photos, then take what changed in the office. Safe to run again at any
// point: every step picks up where the last attempt stopped.

import { sha256 } from "@noble/hashes/sha2.js";
import { bytesToHex } from "@noble/hashes/utils.js";
import { File } from "expo-file-system";

import type { LocalPhoto } from "../types";
import { buildChanges, chunkRanges, featureAction, taskAction, type SyncSummary } from "../utils/syncPlan";
import type { Api } from "./api";
import * as store from "./db";

const CHUNK_BYTES = 256 * 1024;
const PUSH_BATCH = 100;

async function uploadPhoto(api: Api, photo: LocalPhoto): Promise<boolean> {
  const file = new File(photo.path);
  if (!file.exists) {
    await store.markPhotoUploaded(photo.id); // the file is gone; nothing to send
    return false;
  }
  const bytes = new Uint8Array(await file.arrayBuffer());
  let remote = await api.startPhoto({
    uuid: photo.uuid,
    feature_uuid: photo.featureUuid,
    size: bytes.length,
    sha256: bytesToHex(sha256(bytes)),
    latitude: photo.latitude,
    longitude: photo.longitude,
    accuracy_m: photo.accuracyM,
    taken_at: photo.takenAt,
  });
  // Up to two passes: a 409 tells us where the server really is.
  for (let pass = 0; pass < 3 && !remote.complete; pass++) {
    let resumed = false;
    for (const [start, end] of chunkRanges(bytes.length, remote.received, CHUNK_BYTES)) {
      const result = await api.photoChunk(photo.uuid, start, bytes.subarray(start, end));
      if ("resumeFrom" in result) {
        remote = { ...remote, received: result.resumeFrom };
        resumed = true;
        break;
      }
      remote = result;
    }
    if (!resumed) break;
  }
  if (remote.complete) await store.markPhotoUploaded(photo.id);
  return remote.complete;
}

export async function syncProject(api: Api, projectId: number, onStep?: (text: string) => void): Promise<SyncSummary> {
  const summary: SyncSummary = { sent: 0, conflicts: 0, rejected: 0, photos: 0, photosWaiting: 0, received: 0, removed: 0, tasks: 0 };
  const device = await store.deviceId();

  // 1. Send captures, edits and task results.
  onStep?.("Sending captures…");
  const features = await store.listUnsent(projectId);
  const tasks = await store.pendingTasks(projectId);
  const changes = buildChanges(features, tasks);
  const byChange = new Map<string, { feature?: (typeof features)[number]; task?: (typeof tasks)[number] }>();
  for (const feature of features) if (feature.changeId) byChange.set(feature.changeId, { feature });
  for (const task of tasks) if (task.changeId) byChange.set(task.changeId, { task });
  for (let start = 0; start < changes.length; start += PUSH_BATCH) {
    const { results } = await api.push(device, changes.slice(start, start + PUSH_BATCH));
    for (const result of results) {
      const target = result.change_id ? byChange.get(result.change_id) : undefined;
      if (target?.feature) {
        const action = featureAction(target.feature, result);
        if (action.kind === "synced") {
          await store.markSynced(action.uuid, action.serverId, action.version);
          summary.sent += 1;
        } else if (action.kind === "resend-as-edit") {
          await store.markResendAsEdit(action.uuid, action.serverId, action.version);
        } else if (action.kind === "conflict") {
          await store.markConflict(action.uuid);
          summary.conflicts += 1;
        } else {
          await store.markRejected(action.uuid, action.message);
          summary.rejected += 1;
        }
      } else if (target?.task) {
        const action = taskAction(target.task, result);
        if (action.kind === "sent") {
          await store.markTaskSent(action.id);
          summary.sent += 1;
        } else {
          summary.rejected += 1;
        }
      }
    }
  }

  // 2. Photos of features the server now has.
  const photos = await store.photosToUpload(projectId);
  for (const [index, photo] of photos.entries()) {
    onStep?.(`Uploading photo ${index + 1} of ${photos.length}…`);
    if (await uploadPhoto(api, photo)) summary.photos += 1;
  }
  summary.photosWaiting = await store.countPhotosWaiting(projectId);

  // 3. Take what changed in the office.
  onStep?.("Getting updates from the office…");
  const layers = await store.listLayers(projectId);
  const pulled = await api.pull(
    projectId,
    layers.map((l) => l.id),
    await store.lastPull(projectId),
  );
  const applied = await store.applyPull(projectId, pulled);
  await store.setLastPull(projectId, pulled.server_time);
  summary.received = applied.received;
  summary.removed = applied.removed;
  summary.tasks = await store.countOpenTasks(projectId);
  return summary;
}
