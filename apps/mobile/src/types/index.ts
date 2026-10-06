// Shapes shared with the server (see backend/field/services.py and the web
// app's @spatial/map-core types).

export type Position = [number, number]; // [longitude, latitude], WGS 84

export type Geometry =
  | { type: "Point"; coordinates: Position }
  | { type: "LineString"; coordinates: Position[] }
  | { type: "Polygon"; coordinates: Position[][] }
  | { type: "MultiPoint"; coordinates: Position[] }
  | { type: "MultiLineString"; coordinates: Position[][] }
  | { type: "MultiPolygon"; coordinates: Position[][][] };

export type GeometryType = "point" | "line" | "polygon";
export type FieldType = "text" | "integer" | "decimal" | "boolean" | "date" | "choice";

export interface SchemaField {
  name: string;
  label?: string;
  type: FieldType;
  required?: boolean;
  choices?: (string | number)[];
  default?: unknown;
}

export interface SymbolStyle {
  fill: string;
  stroke: string;
  stroke_width: number;
  point_radius: number;
  fill_opacity: number;
}

export type LayerStyle =
  | ({ kind: "single"; label_field?: string | null } & SymbolStyle)
  | {
      kind: "categorized";
      field: string;
      categories: ({ value: unknown } & SymbolStyle)[];
      default: SymbolStyle;
      label_field?: string | null;
    };

export interface Tokens {
  access: string;
  refresh: string;
}

export interface Membership {
  district: { id: number; name: string; code: string };
  role: string;
  permissions: string[];
}

export interface Me {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  is_system_admin: boolean;
  memberships: Membership[];
}

export interface ServerProject {
  id: number;
  name: string;
  community: string;
  layer_count: number;
  crs_detail: { code: string; name: string };
}

export interface ServerLayer {
  id: number;
  name: string;
  domain: string;
  geometry_type: GeometryType;
  feature_count: number;
}

export interface PackageCrs {
  code: string;
  name: string;
  kind: "projected" | "geographic";
  units: string;
  unit_to_metre: number | null;
  proj4: string;
}

export interface PackageLayer {
  id: number;
  name: string;
  domain: string;
  geometry_type: GeometryType;
  schema: SchemaField[];
  style: LayerStyle;
  order: number;
  feature_count: number;
}

export interface PackageFeature {
  id: number;
  uuid: string;
  version: number;
  verified: boolean;
  properties: Record<string, unknown>;
  geometry: Geometry;
}

export interface OfflineBasemap {
  id: number;
  name: string;
  attribution: string;
  min_zoom: number;
  max_zoom: number;
}

export interface FieldPackage {
  format: number;
  generated_at: string;
  project: {
    id: number;
    name: string;
    community: string;
    district: number;
    boundary: Geometry | null;
    boundary_status: string;
    bbox: [number, number, number, number] | null;
    crs: PackageCrs;
  };
  layers: PackageLayer[];
  features: Record<string, PackageFeature[]>;
  feature_total: number;
  clipped_to_boundary: boolean;
  offline_basemaps: OfflineBasemap[];
}

// --- On the device ---------------------------------------------------------------------

export interface LocalProject {
  id: number;
  district: number;
  name: string;
  community: string;
  crs: PackageCrs;
  boundary: Geometry | null;
  bbox: [number, number, number, number] | null;
  downloadedAt: string;
  packageBytes: number;
  basemapPath: string | null;
  basemapName: string | null;
  basemapBytes: number;
  offlineBasemaps: OfflineBasemap[];
}

export interface LocalLayer {
  id: number;
  projectId: number;
  name: string;
  domain: string;
  geometryType: GeometryType;
  schema: SchemaField[];
  style: LayerStyle;
  sort: number;
  visible: boolean;
}

/** synced: same as the server. new: captured here. edited: a server feature
 * changed here. conflict: the office changed it too; waiting for the office to decide. */
export type FeatureState = "synced" | "new" | "edited" | "conflict";
export type CaptureMethod = "gps" | "gps_track" | "drawn";

export interface LocalFeature {
  localId: number;
  uuid: string;
  serverId: number | null;
  layerId: number;
  projectId: number;
  geometry: Geometry;
  properties: Record<string, unknown>;
  version: number;
  verified: boolean;
  state: FeatureState;
  capturedAt: string | null;
  capturedBy: string | null;
  method: CaptureMethod | null;
  /** Horizontal accuracy in metres (GPS captures): the mean for an averaged point, the worst reading for a track. */
  accuracyM: number | null;
  fixTime: string | null;
  readings: number | null;
  notes: string;
  /** Identifies this pending change to the server; renewed whenever the feature is saved here. */
  changeId: string | null;
  /** Why the server refused it, if it did. */
  syncError: string | null;
}

export interface LocalPhoto {
  id: number;
  featureUuid: string;
  path: string;
  width: number;
  height: number;
  bytes: number;
  latitude: number | null;
  longitude: number | null;
  accuracyM: number | null;
  takenAt: string;
  uuid: string;
  uploaded: boolean;
}

export type TaskOutcome = "confirmed" | "corrected" | "not_found";

/** A ground-truthing task: check one feature on the ground. */
export interface LocalTask {
  id: number;
  projectId: number;
  featureUuid: string;
  layerId: number;
  item: string;
  status: "open" | "done";
  outcome: TaskOutcome | "";
  notes: string;
  /** Done on this device, not yet sent. */
  pending: boolean;
  changeId: string | null;
}

// --- Sync messages (see backend/sync) ----------------------------------------------------------

export type SyncChange =
  | {
      change_id: string;
      op: "create";
      layer: number;
      feature_uuid: string;
      geometry: Geometry;
      properties: Record<string, unknown>;
      capture: Record<string, unknown>;
    }
  | {
      change_id: string;
      op: "update";
      feature_uuid: string;
      base_version: number;
      properties: Record<string, unknown>;
      capture: Record<string, unknown>;
    }
  | { change_id: string; op: "task"; task: { id: number; outcome: TaskOutcome; notes: string } };

export interface SyncResult {
  change_id: string | null;
  status: "applied" | "conflict" | "rejected";
  feature?: { id: number; uuid: string; version: number };
  task?: number;
  conflict?: number;
  duplicate?: boolean;
  repeat?: boolean;
  errors?: string[];
}

export interface PullResponse {
  server_time: string;
  full: boolean;
  layers: Omit<PackageLayer, "feature_count">[];
  features: (PackageFeature & { layer: number })[];
  deleted: string[];
  tasks: { id: number; feature_uuid: string; layer: number; status: "open" | "done"; outcome: TaskOutcome | ""; item: string }[];
}

export interface RemotePhoto {
  uuid: string;
  size: number;
  received: number;
  complete: boolean;
}

/** One GPS reading. */
export interface Fix {
  longitude: number;
  latitude: number;
  accuracy: number | null;
  timestamp: number;
}
