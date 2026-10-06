// The device's own database (SQLite). Everything the field officer needs
// offline lives here: downloaded projects, layers and features, and what was
// captured on the device.

import * as Crypto from "expo-crypto";
import * as SQLite from "expo-sqlite";

import type {
  CaptureMethod,
  FeatureState,
  FieldPackage,
  Geometry,
  LocalFeature,
  LocalLayer,
  LocalPhoto,
  LocalProject,
  LocalTask,
  OfflineBasemap,
  PullResponse,
  TaskOutcome,
} from "../types";
import { serverMayReplace } from "../utils/syncPlan";

let handle: Promise<SQLite.SQLiteDatabase> | null = null;

const SCHEMA = `
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY NOT NULL, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS projects (
  id INTEGER PRIMARY KEY NOT NULL,
  district INTEGER NOT NULL,
  name TEXT NOT NULL,
  community TEXT NOT NULL DEFAULT '',
  crs_json TEXT NOT NULL,
  boundary_json TEXT,
  bbox_json TEXT,
  downloaded_at TEXT NOT NULL,
  package_bytes INTEGER NOT NULL DEFAULT 0,
  basemap_path TEXT,
  basemap_name TEXT,
  basemap_bytes INTEGER NOT NULL DEFAULT 0,
  offline_basemaps_json TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS layers (
  id INTEGER PRIMARY KEY NOT NULL,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  domain TEXT NOT NULL,
  geometry_type TEXT NOT NULL,
  schema_json TEXT NOT NULL,
  style_json TEXT NOT NULL,
  sort INTEGER NOT NULL DEFAULT 0,
  visible INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS features (
  local_id INTEGER PRIMARY KEY AUTOINCREMENT,
  uuid TEXT NOT NULL UNIQUE,
  server_id INTEGER,
  layer_id INTEGER NOT NULL,
  project_id INTEGER NOT NULL,
  geometry_json TEXT NOT NULL,
  properties_json TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 0,
  verified INTEGER NOT NULL DEFAULT 0,
  state TEXT NOT NULL DEFAULT 'synced',
  captured_at TEXT,
  captured_by TEXT,
  method TEXT,
  accuracy_m REAL,
  fix_time TEXT,
  readings INTEGER,
  notes TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS features_layer ON features (layer_id);
CREATE INDEX IF NOT EXISTS features_project_state ON features (project_id, state);
CREATE TABLE IF NOT EXISTS photos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  feature_uuid TEXT NOT NULL,
  path TEXT NOT NULL,
  width INTEGER NOT NULL,
  height INTEGER NOT NULL,
  bytes INTEGER NOT NULL,
  latitude REAL,
  longitude REAL,
  accuracy_m REAL,
  taken_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS photos_feature ON photos (feature_uuid);
`;

// Changes to the database after its first version, applied once each, in order.
// Version 2 (sync): change ids, refusal messages, photo upload state, tasks.
const MIGRATIONS: string[] = [
  `ALTER TABLE features ADD COLUMN change_id TEXT;
   ALTER TABLE features ADD COLUMN sync_error TEXT;
   ALTER TABLE photos ADD COLUMN uuid TEXT;
   ALTER TABLE photos ADD COLUMN uploaded INTEGER NOT NULL DEFAULT 0;
   CREATE TABLE IF NOT EXISTS tasks (
     id INTEGER PRIMARY KEY NOT NULL,
     project_id INTEGER NOT NULL,
     feature_uuid TEXT NOT NULL,
     layer_id INTEGER NOT NULL,
     item TEXT NOT NULL DEFAULT '',
     status TEXT NOT NULL DEFAULT 'open',
     outcome TEXT NOT NULL DEFAULT '',
     notes TEXT NOT NULL DEFAULT '',
     pending INTEGER NOT NULL DEFAULT 0,
     change_id TEXT
   );
   CREATE INDEX IF NOT EXISTS tasks_project ON tasks (project_id, status);`,
];

export function db(): Promise<SQLite.SQLiteDatabase> {
  handle ??= (async () => {
    const database = await SQLite.openDatabaseAsync("spatial-field.db");
    await database.execAsync(SCHEMA);
    const row = await database.getFirstAsync<{ user_version: number }>("PRAGMA user_version");
    for (let version = row?.user_version ?? 0; version < MIGRATIONS.length; version++) {
      await database.execAsync(`${MIGRATIONS[version]}\nPRAGMA user_version = ${version + 1};`);
    }
    // Captures made before sync existed get the ids sync needs.
    await database.runAsync("UPDATE features SET change_id = lower(hex(randomblob(16))) WHERE change_id IS NULL AND state <> 'synced'");
    const old = await database.getAllAsync<{ id: number }>("SELECT id FROM photos WHERE uuid IS NULL");
    for (const photo of old) await database.runAsync("UPDATE photos SET uuid = ? WHERE id = ?", [Crypto.randomUUID(), photo.id]);
    return database;
  })();
  return handle;
}

// --- Small key/value store (server address, chosen district, cached profile) -------------

export async function getMeta(key: string): Promise<string | null> {
  const row = await (await db()).getFirstAsync<{ value: string }>("SELECT value FROM meta WHERE key = ?", [key]);
  return row?.value ?? null;
}

export async function setMeta(key: string, value: string | null): Promise<void> {
  const database = await db();
  if (value === null) await database.runAsync("DELETE FROM meta WHERE key = ?", [key]);
  else await database.runAsync("INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", [key, value]);
}

// --- Rows to objects -------------------------------------------------------------------------

interface ProjectRow {
  id: number;
  district: number;
  name: string;
  community: string;
  crs_json: string;
  boundary_json: string | null;
  bbox_json: string | null;
  downloaded_at: string;
  package_bytes: number;
  basemap_path: string | null;
  basemap_name: string | null;
  basemap_bytes: number;
  offline_basemaps_json: string;
}

function toProject(row: ProjectRow): LocalProject {
  return {
    id: row.id,
    district: row.district,
    name: row.name,
    community: row.community,
    crs: JSON.parse(row.crs_json),
    boundary: row.boundary_json ? (JSON.parse(row.boundary_json) as Geometry) : null,
    bbox: row.bbox_json ? JSON.parse(row.bbox_json) : null,
    downloadedAt: row.downloaded_at,
    packageBytes: row.package_bytes,
    basemapPath: row.basemap_path,
    basemapName: row.basemap_name,
    basemapBytes: row.basemap_bytes,
    offlineBasemaps: JSON.parse(row.offline_basemaps_json) as OfflineBasemap[],
  };
}

interface LayerRow {
  id: number;
  project_id: number;
  name: string;
  domain: string;
  geometry_type: string;
  schema_json: string;
  style_json: string;
  sort: number;
  visible: number;
}

function toLayer(row: LayerRow): LocalLayer {
  return {
    id: row.id,
    projectId: row.project_id,
    name: row.name,
    domain: row.domain,
    geometryType: row.geometry_type as LocalLayer["geometryType"],
    schema: JSON.parse(row.schema_json),
    style: JSON.parse(row.style_json),
    sort: row.sort,
    visible: row.visible === 1,
  };
}

interface FeatureRow {
  local_id: number;
  uuid: string;
  server_id: number | null;
  layer_id: number;
  project_id: number;
  geometry_json: string;
  properties_json: string;
  version: number;
  verified: number;
  state: string;
  captured_at: string | null;
  captured_by: string | null;
  method: string | null;
  accuracy_m: number | null;
  fix_time: string | null;
  readings: number | null;
  notes: string;
  change_id: string | null;
  sync_error: string | null;
}

function toFeature(row: FeatureRow): LocalFeature {
  return {
    localId: row.local_id,
    uuid: row.uuid,
    serverId: row.server_id,
    layerId: row.layer_id,
    projectId: row.project_id,
    geometry: JSON.parse(row.geometry_json) as Geometry,
    properties: JSON.parse(row.properties_json),
    version: row.version,
    verified: row.verified === 1,
    state: row.state as FeatureState,
    capturedAt: row.captured_at,
    capturedBy: row.captured_by,
    method: row.method as CaptureMethod | null,
    accuracyM: row.accuracy_m,
    fixTime: row.fix_time,
    readings: row.readings,
    notes: row.notes,
    changeId: row.change_id,
    syncError: row.sync_error,
  };
}

// --- Projects and packages -----------------------------------------------------------------

export async function listProjects(district: number | null): Promise<LocalProject[]> {
  const database = await db();
  const rows =
    district === null
      ? await database.getAllAsync<ProjectRow>("SELECT * FROM projects ORDER BY name")
      : await database.getAllAsync<ProjectRow>("SELECT * FROM projects WHERE district = ? ORDER BY name", [district]);
  return rows.map(toProject);
}

export async function getProject(id: number): Promise<LocalProject | null> {
  const row = await (await db()).getFirstAsync<ProjectRow>("SELECT * FROM projects WHERE id = ?", [id]);
  return row ? toProject(row) : null;
}

/** Stores a downloaded package. Downloading again refreshes what came from the
 * server but never touches what was captured or changed on this device. */
export async function savePackage(pkg: FieldPackage, packageBytes: number): Promise<{ kept: number }> {
  const database = await db();
  let kept = 0;
  await database.withExclusiveTransactionAsync(async (txn) => {
    const p = pkg.project;
    await txn.runAsync(
      `INSERT INTO projects (id, district, name, community, crs_json, boundary_json, bbox_json, downloaded_at, package_bytes, offline_basemaps_json)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
       ON CONFLICT(id) DO UPDATE SET district = excluded.district, name = excluded.name, community = excluded.community,
         crs_json = excluded.crs_json, boundary_json = excluded.boundary_json, bbox_json = excluded.bbox_json,
         downloaded_at = excluded.downloaded_at, package_bytes = excluded.package_bytes,
         offline_basemaps_json = excluded.offline_basemaps_json`,
      [
        p.id,
        p.district,
        p.name,
        p.community,
        JSON.stringify(p.crs),
        p.boundary ? JSON.stringify(p.boundary) : null,
        p.bbox ? JSON.stringify(p.bbox) : null,
        pkg.generated_at,
        packageBytes,
        JSON.stringify(pkg.offline_basemaps),
      ],
    );
    for (const layer of pkg.layers) {
      await txn.runAsync(
        `INSERT INTO layers (id, project_id, name, domain, geometry_type, schema_json, style_json, sort)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?)
         ON CONFLICT(id) DO UPDATE SET name = excluded.name, domain = excluded.domain, geometry_type = excluded.geometry_type,
           schema_json = excluded.schema_json, style_json = excluded.style_json, sort = excluded.sort`,
        [layer.id, p.id, layer.name, layer.domain, layer.geometry_type, JSON.stringify(layer.schema), JSON.stringify(layer.style), layer.order],
      );
      // Only untouched server copies are replaced.
      await txn.runAsync("DELETE FROM features WHERE layer_id = ? AND state = 'synced'", [layer.id]);
      const statement = await txn.prepareAsync(
        `INSERT INTO features (uuid, server_id, layer_id, project_id, geometry_json, properties_json, version, verified, state)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'synced') ON CONFLICT(uuid) DO NOTHING`,
      );
      try {
        for (const feature of pkg.features[String(layer.id)] ?? []) {
          const result = await statement.executeAsync([
            feature.uuid,
            feature.id,
            layer.id,
            p.id,
            JSON.stringify(feature.geometry),
            JSON.stringify(feature.properties),
            feature.version,
            feature.verified ? 1 : 0,
          ]);
          if (result.changes === 0) kept += 1; // changed on this device: left alone
        }
      } finally {
        await statement.finalizeAsync();
      }
    }
  });
  return { kept };
}

export async function setBasemap(projectId: number, path: string | null, name: string | null, bytes: number): Promise<void> {
  await (await db()).runAsync("UPDATE projects SET basemap_path = ?, basemap_name = ?, basemap_bytes = ? WHERE id = ?", [path, name, bytes, projectId]);
}

/** Removes a project's downloaded copy. Refuses while it holds captures that
 * haven't been sent to the server. */
export async function removeProject(projectId: number): Promise<{ removed: boolean; unsent: number }> {
  const database = await db();
  const unsent = await countUnsent(projectId);
  if (unsent > 0) return { removed: false, unsent };
  await database.withExclusiveTransactionAsync(async (txn) => {
    await txn.runAsync("DELETE FROM features WHERE project_id = ?", [projectId]);
    await txn.runAsync("DELETE FROM tasks WHERE project_id = ?", [projectId]);
    await txn.runAsync("DELETE FROM layers WHERE project_id = ?", [projectId]);
    await txn.runAsync("DELETE FROM projects WHERE id = ?", [projectId]);
  });
  return { removed: true, unsent: 0 };
}

// --- Layers and features ---------------------------------------------------------------------

export async function listLayers(projectId: number): Promise<LocalLayer[]> {
  const rows = await (await db()).getAllAsync<LayerRow>("SELECT * FROM layers WHERE project_id = ? ORDER BY sort DESC, id", [projectId]);
  return rows.map(toLayer);
}

export async function setLayerVisible(layerId: number, visible: boolean): Promise<void> {
  await (await db()).runAsync("UPDATE layers SET visible = ? WHERE id = ?", [visible ? 1 : 0, layerId]);
}

export async function listFeatures(layerId: number): Promise<LocalFeature[]> {
  const rows = await (await db()).getAllAsync<FeatureRow>("SELECT * FROM features WHERE layer_id = ? ORDER BY local_id", [layerId]);
  return rows.map(toFeature);
}

export async function getFeature(uuid: string): Promise<LocalFeature | null> {
  const row = await (await db()).getFirstAsync<FeatureRow>("SELECT * FROM features WHERE uuid = ?", [uuid]);
  return row ? toFeature(row) : null;
}

export async function listUnsent(projectId: number): Promise<LocalFeature[]> {
  const rows = await (await db()).getAllAsync<FeatureRow>(
    "SELECT * FROM features WHERE project_id = ? AND state <> 'synced' ORDER BY captured_at DESC, local_id DESC",
    [projectId],
  );
  return rows.map(toFeature);
}

export async function countUnsent(projectId?: number): Promise<number> {
  const database = await db();
  const row =
    projectId === undefined
      ? await database.getFirstAsync<{ n: number }>("SELECT count(*) AS n FROM features WHERE state <> 'synced'")
      : await database.getFirstAsync<{ n: number }>("SELECT count(*) AS n FROM features WHERE state <> 'synced' AND project_id = ?", [projectId]);
  return row?.n ?? 0;
}

export interface NewCapture {
  uuid: string;
  layerId: number;
  projectId: number;
  geometry: Geometry;
  properties: Record<string, unknown>;
  capturedBy: string;
  method: CaptureMethod;
  accuracyM: number | null;
  fixTime: string | null;
  readings: number | null;
  notes: string;
}

export async function insertCapture(capture: NewCapture): Promise<void> {
  await (await db()).runAsync(
    `INSERT INTO features (change_id, uuid, layer_id, project_id, geometry_json, properties_json, version, state, captured_at, captured_by, method, accuracy_m, fix_time, readings, notes)
     VALUES (?, ?, ?, ?, ?, ?, 0, 'new', ?, ?, ?, ?, ?, ?, ?)`,
    [
      Crypto.randomUUID(),
      capture.uuid,
      capture.layerId,
      capture.projectId,
      JSON.stringify(capture.geometry),
      JSON.stringify(capture.properties),
      new Date().toISOString(),
      capture.capturedBy,
      capture.method,
      capture.accuracyM,
      capture.fixTime,
      capture.readings,
      capture.notes,
    ],
  );
}

/** Changes a feature's attributes and notes. A downloaded feature becomes
 * "edited" (its base version is kept for sync); a new one stays "new". */
export async function updateAttributes(uuid: string, properties: Record<string, unknown>, notes: string, by: string): Promise<void> {
  await (await db()).runAsync(
    // A new change id each time: the server must not mistake this for a send it already has.
    `UPDATE features SET properties_json = ?, notes = ?, captured_by = ?, captured_at = ?, change_id = ?, sync_error = NULL,
       state = CASE WHEN state IN ('synced', 'conflict') THEN 'edited' ELSE state END WHERE uuid = ?`,
    [JSON.stringify(properties), notes, by, new Date().toISOString(), Crypto.randomUUID(), uuid],
  );
}

/** Deletes a feature captured on this device (downloaded ones can't be deleted here). */
export async function deleteCapture(uuid: string): Promise<LocalPhoto[]> {
  const database = await db();
  const photos = await listPhotos(uuid);
  await database.withExclusiveTransactionAsync(async (txn) => {
    await txn.runAsync("DELETE FROM photos WHERE feature_uuid = ?", [uuid]);
    await txn.runAsync("DELETE FROM features WHERE uuid = ? AND state = 'new'", [uuid]);
  });
  return photos;
}

// --- Photos ------------------------------------------------------------------------------------

interface PhotoRow {
  id: number;
  feature_uuid: string;
  path: string;
  width: number;
  height: number;
  bytes: number;
  latitude: number | null;
  longitude: number | null;
  accuracy_m: number | null;
  taken_at: string;
  uuid: string;
  uploaded: number;
}

function toPhoto(row: PhotoRow): LocalPhoto {
  return {
    id: row.id,
    featureUuid: row.feature_uuid,
    path: row.path,
    width: row.width,
    height: row.height,
    bytes: row.bytes,
    latitude: row.latitude,
    longitude: row.longitude,
    accuracyM: row.accuracy_m,
    takenAt: row.taken_at,
    uuid: row.uuid,
    uploaded: row.uploaded === 1,
  };
}

export async function listPhotos(featureUuid: string): Promise<LocalPhoto[]> {
  const rows = await (await db()).getAllAsync<PhotoRow>("SELECT * FROM photos WHERE feature_uuid = ? ORDER BY id", [featureUuid]);
  return rows.map(toPhoto);
}

export async function insertPhoto(photo: Omit<LocalPhoto, "id" | "uuid" | "uploaded">): Promise<void> {
  await (await db()).runAsync(
    "INSERT INTO photos (uuid, feature_uuid, path, width, height, bytes, latitude, longitude, accuracy_m, taken_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
    [Crypto.randomUUID(), photo.featureUuid, photo.path, photo.width, photo.height, photo.bytes, photo.latitude, photo.longitude, photo.accuracyM, photo.takenAt],
  );
}

export async function deletePhoto(id: number): Promise<void> {
  await (await db()).runAsync("DELETE FROM photos WHERE id = ?", [id]);
}

export async function photoBytes(): Promise<number> {
  const row = await (await db()).getFirstAsync<{ n: number | null }>("SELECT sum(bytes) AS n FROM photos");
  return row?.n ?? 0;
}

// --- Sync ------------------------------------------------------------------------------------------

/** A stable id for this installation, sent with every push. */
export async function deviceId(): Promise<string> {
  let id = await getMeta("device_id");
  if (!id) {
    id = Crypto.randomUUID();
    await setMeta("device_id", id);
  }
  return id;
}

export const lastPull = (projectId: number) => getMeta(`last_pull.${projectId}`);
export const setLastPull = (projectId: number, serverTime: string) => setMeta(`last_pull.${projectId}`, serverTime);

export async function markSynced(uuid: string, serverId: number, version: number): Promise<void> {
  await (await db()).runAsync("UPDATE features SET state = 'synced', server_id = ?, version = ?, change_id = NULL, sync_error = NULL WHERE uuid = ?", [serverId, version, uuid]);
}

/** The server has the feature but not the latest values: next push sends them as an edit. */
export async function markResendAsEdit(uuid: string, serverId: number, version: number): Promise<void> {
  await (await db()).runAsync("UPDATE features SET state = 'edited', server_id = ?, version = ?, change_id = ?, sync_error = NULL WHERE uuid = ?", [
    serverId,
    version,
    Crypto.randomUUID(),
    uuid,
  ]);
}

export async function markConflict(uuid: string): Promise<void> {
  await (await db()).runAsync("UPDATE features SET state = 'conflict', sync_error = NULL WHERE uuid = ?", [uuid]);
}

export async function markRejected(uuid: string, message: string): Promise<void> {
  await (await db()).runAsync("UPDATE features SET sync_error = ? WHERE uuid = ?", [message, uuid]);
}

/** Photos whose feature is on the server and that haven't been uploaded yet. */
export async function photosToUpload(projectId: number): Promise<LocalPhoto[]> {
  const rows = await (await db()).getAllAsync<PhotoRow>(
    `SELECT p.* FROM photos p JOIN features f ON f.uuid = p.feature_uuid
     WHERE f.project_id = ? AND f.server_id IS NOT NULL AND p.uploaded = 0 ORDER BY p.id`,
    [projectId],
  );
  return rows.map(toPhoto);
}

export async function countPhotosWaiting(projectId: number): Promise<number> {
  const row = await (await db()).getFirstAsync<{ n: number }>(
    "SELECT count(*) AS n FROM photos p JOIN features f ON f.uuid = p.feature_uuid WHERE f.project_id = ? AND p.uploaded = 0",
    [projectId],
  );
  return row?.n ?? 0;
}

export async function markPhotoUploaded(id: number): Promise<void> {
  await (await db()).runAsync("UPDATE photos SET uploaded = 1 WHERE id = ?", [id]);
}

/** Applies what the server sent. Nothing captured or changed on this device
 * and not yet sent is ever replaced or removed. */
export async function applyPull(projectId: number, pulled: PullResponse): Promise<{ received: number; removed: number }> {
  const database = await db();
  let received = 0;
  let removed = 0;
  await database.withExclusiveTransactionAsync(async (txn) => {
    for (const layer of pulled.layers) {
      await txn.runAsync("UPDATE layers SET name = ?, domain = ?, schema_json = ?, style_json = ?, sort = ? WHERE id = ?", [
        layer.name,
        layer.domain,
        JSON.stringify(layer.schema),
        JSON.stringify(layer.style),
        layer.order,
        layer.id,
      ]);
    }
    for (const feature of pulled.features) {
      const row = await txn.getFirstAsync<FeatureRow>("SELECT * FROM features WHERE uuid = ?", [feature.uuid]);
      const local = row ? toFeature(row) : undefined;
      if (!serverMayReplace(local)) continue;
      // Our own send coming back unchanged isn't news.
      if (local && local.state === "synced" && local.version === feature.version && local.verified === feature.verified) continue;
      if (local) {
        await txn.runAsync(
          "UPDATE features SET server_id = ?, layer_id = ?, geometry_json = ?, properties_json = ?, version = ?, verified = ?, state = 'synced', change_id = NULL, sync_error = NULL WHERE uuid = ?",
          [feature.id, feature.layer, JSON.stringify(feature.geometry), JSON.stringify(feature.properties), feature.version, feature.verified ? 1 : 0, feature.uuid],
        );
      } else {
        await txn.runAsync(
          "INSERT INTO features (uuid, server_id, layer_id, project_id, geometry_json, properties_json, version, verified, state) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'synced')",
          [feature.uuid, feature.id, feature.layer, projectId, JSON.stringify(feature.geometry), JSON.stringify(feature.properties), feature.version, feature.verified ? 1 : 0],
        );
      }
      received += 1;
    }
    for (const uuid of pulled.deleted) {
      const result = await txn.runAsync("DELETE FROM features WHERE uuid = ? AND state IN ('synced', 'conflict')", [uuid]);
      removed += result.changes;
    }
    for (const task of pulled.tasks) {
      // A result recorded here and not yet sent stays as it is.
      await txn.runAsync(
        `INSERT INTO tasks (id, project_id, feature_uuid, layer_id, item, status, outcome) VALUES (?, ?, ?, ?, ?, ?, ?)
         ON CONFLICT(id) DO UPDATE SET status = excluded.status, outcome = excluded.outcome, item = excluded.item WHERE tasks.pending = 0`,
        [task.id, projectId, task.feature_uuid, task.layer, task.item, task.status, task.outcome],
      );
    }
  });
  return { received, removed };
}

// --- Ground-truthing tasks -------------------------------------------------------------------------

interface TaskRow {
  id: number;
  project_id: number;
  feature_uuid: string;
  layer_id: number;
  item: string;
  status: string;
  outcome: string;
  notes: string;
  pending: number;
  change_id: string | null;
}

function toTask(row: TaskRow): LocalTask {
  return {
    id: row.id,
    projectId: row.project_id,
    featureUuid: row.feature_uuid,
    layerId: row.layer_id,
    item: row.item,
    status: row.status as LocalTask["status"],
    outcome: row.outcome as LocalTask["outcome"],
    notes: row.notes,
    pending: row.pending === 1,
    changeId: row.change_id,
  };
}

/** Tasks still to do (and those done here but not yet sent, so they can be reviewed). */
export async function listTasks(projectId: number): Promise<LocalTask[]> {
  const rows = await (await db()).getAllAsync<TaskRow>("SELECT * FROM tasks WHERE project_id = ? AND (status = 'open' OR pending = 1) ORDER BY pending, id", [projectId]);
  return rows.map(toTask);
}

export async function pendingTasks(projectId: number): Promise<LocalTask[]> {
  const rows = await (await db()).getAllAsync<TaskRow>("SELECT * FROM tasks WHERE project_id = ? AND pending = 1 ORDER BY id", [projectId]);
  return rows.map(toTask);
}

export async function countOpenTasks(projectId: number): Promise<number> {
  const row = await (await db()).getFirstAsync<{ n: number }>("SELECT count(*) AS n FROM tasks WHERE project_id = ? AND status = 'open' AND pending = 0", [projectId]);
  return row?.n ?? 0;
}

/** Records what was found on the ground; sent at the next sync. */
export async function completeTask(id: number, outcome: TaskOutcome, notes: string): Promise<void> {
  await (await db()).runAsync("UPDATE tasks SET status = 'done', outcome = ?, notes = ?, pending = 1, change_id = ? WHERE id = ?", [outcome, notes, Crypto.randomUUID(), id]);
}

export async function reopenTask(id: number): Promise<void> {
  await (await db()).runAsync("UPDATE tasks SET status = 'open', outcome = '', pending = 0, change_id = NULL WHERE id = ? AND pending = 1", [id]);
}

export async function markTaskSent(id: number): Promise<void> {
  await (await db()).runAsync("UPDATE tasks SET pending = 0, change_id = NULL WHERE id = ?", [id]);
}
