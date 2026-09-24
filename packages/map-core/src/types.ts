// Shapes returned by the backend API (see /api/schema/).

export type Role = "district_admin" | "planner" | "field_officer" | "viewer";

export const ROLE_LABELS: Record<Role, string> = {
  district_admin: "District administrator",
  planner: "Physical planner",
  field_officer: "Field officer",
  viewer: "Viewer",
};

export type Permission =
  | "district.view"
  | "membership.view"
  | "membership.manage"
  | "audit.view"
  | "crs.manage"
  | "project.view"
  | "project.edit"
  | "layer.edit"
  | "feature.edit"
  | "basemap.manage";

export interface DistrictBrief {
  id: number;
  name: string;
  code: string;
}

export interface MyMembership {
  district: DistrictBrief;
  role: Role;
  permissions: Permission[];
}

export interface Me {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  is_system_admin: boolean;
  memberships: MyMembership[];
}

export interface Tokens {
  access: string;
  refresh: string;
}

export interface LoginResponse extends Tokens {
  user: Me;
}

export interface Region {
  id: number;
  name: string;
  code: string;
}

export type DistrictKind = "metropolitan" | "municipal" | "district";

export interface District {
  id: number;
  name: string;
  code: string;
  kind: DistrictKind;
  region: number;
  region_name: string;
  is_active: boolean;
}

export interface User {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  is_active: boolean;
  is_system_admin: boolean;
  is_locked: boolean;
  last_login: string | null;
  date_joined: string;
}

export interface Member {
  id: number;
  user: Pick<User, "id" | "email" | "first_name" | "last_name" | "is_active">;
  role: Role;
  is_active: boolean;
  created_at: string;
}

export type AuditAction = "INSERT" | "UPDATE" | "DELETE";

export interface AuditEntry {
  id: number;
  occurred_at: string;
  table_name: string;
  row_id: string;
  action: AuditAction;
  changed_fields: string[];
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  user_id: number | null;
  user_email: string | null;
  district_id: number | null;
}

export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface AuditFilters {
  table?: string;
  action?: AuditAction;
  user_id?: number;
  since?: string;
  until?: string;
  page?: number;
}

// --- Coordinate reference systems (Phase 2) ---------------------------------------

export interface CoordinateSystem {
  id: number;
  code: string;
  name: string;
  srid: number;
  kind: "projected" | "geographic";
  units: string;
  unit_to_metre: number | null;
  area_of_use: string;
  bounds: [number, number, number, number] | null;
  notes: string;
  is_builtin: boolean;
  scope: "builtin" | "global" | "district";
  is_active: boolean;
  /** For web maps: includes the server's datum shift (+towgs84). */
  proj4: string;
  wkt: string;
}

export type DefaultSource = "user" | "district" | "system";

export interface CrsDefaults {
  system: CoordinateSystem;
  district: CoordinateSystem | null;
  user: CoordinateSystem | null;
  effective: { crs: CoordinateSystem; source: DefaultSource };
}

export interface CrsOperation {
  name: string;
  pipeline: string;
  /** Stated accuracy in metres; null when PROJ doesn't know it. */
  accuracy_m: number | null;
  pinned: boolean;
}

export interface DefinitionPreview {
  name: string;
  kind: string;
  units: string;
  area_of_use: string;
  bounds: number[] | null;
  proj4: string;
  epsg: number | null;
}

export type Position = [number, number];

// --- Projects, layers, features (Phase 3) -----------------------------------------------

export type Domain = "A" | "B" | "C" | "D" | "E" | "F" | "G" | "H" | "I" | "J" | "other";

export const DOMAIN_LABELS: Record<Domain, string> = {
  A: "A. Territory",
  B: "B. Land & parcels",
  C: "C. Buildings & properties",
  D: "D. Streets & addressing",
  E: "E. Infrastructure & services",
  F: "F. Environment & physical geography",
  G: "G. Development activity",
  H: "H. Socio-economic & demographic",
  I: "I. Projects & investment",
  J: "J. Planning & policy",
  other: "Other",
};

export type GeometryType = "point" | "line" | "polygon";
export type FieldType = "text" | "integer" | "decimal" | "boolean" | "date" | "choice";

export interface SchemaField {
  name: string;
  label: string;
  type: FieldType;
  required: boolean;
  choices?: (string | number)[];
  default?: unknown;
}

export interface Symbol {
  fill: string;
  stroke: string;
  stroke_width: number;
  point_radius: number;
  fill_opacity: number;
}

export type LayerStyle =
  | ({ kind: "single"; label_field: string | null } & Symbol)
  | {
      kind: "categorized";
      field: string;
      categories: ({ value: unknown } & Symbol)[];
      default: Symbol;
      label_field: string | null;
    };

export interface CrsBrief {
  id: number;
  code: string;
  name: string;
  units: string;
  kind: "projected" | "geographic";
}

export interface Project {
  id: number;
  name: string;
  community: string;
  description: string;
  crs: number;
  crs_detail: CrsBrief;
  status: "draft" | "active" | "archived";
  layer_count: number;
  created_at: string;
  updated_at: string;
}

export interface Layer {
  id: number;
  project: number;
  name: string;
  domain: Domain;
  geometry_type: GeometryType;
  crs: number;
  crs_detail: CrsBrief;
  schema: SchemaField[];
  style: LayerStyle;
  order: number;
  visible: boolean;
  opacity: number;
  source: "drawn" | "upload" | "field" | "derived";
  feature_count: number;
  created_at: string;
  updated_at: string;
}

export interface GeoJSONGeometry {
  type: string;
  coordinates: unknown;
}

export interface MapFeature {
  type: "Feature";
  id: number;
  geometry: GeoJSONGeometry | null;
  properties: Record<string, unknown>;
  meta: { uuid: string; version: number; origin: string; verified: boolean; updated_at: string };
}

export interface FeaturePage {
  type: "FeatureCollection";
  crs_code: string;
  numberMatched: number;
  numberReturned: number;
  next_offset: number | null;
  features: MapFeature[];
}

// --- Basemaps (Phase 4) ------------------------------------------------------------------

export type BasemapKind = "xyz" | "wms" | "wmts" | "google" | "bing";
export type BasemapPreset = "osm" | "esri_imagery" | "google_roadmap" | "google_satellite" | "bing_aerial";

export interface Basemap {
  id: number;
  name: string;
  kind: BasemapKind;
  preset: string;
  url: string;
  layers: string;
  attribution: string;
  min_zoom: number;
  max_zoom: number;
  requires_key: boolean;
  has_key: boolean;
  offline_cache_allowed: boolean;
  notes: string;
  is_active: boolean;
  order: number;
  scope: "global" | "district";
}

/** What the map needs to draw a basemap (Google comes back as ready-made XYZ). */
export interface BasemapConfig {
  id: number;
  name: string;
  kind: Exclude<BasemapKind, "google">;
  url: string;
  layers: string;
  attribution: string;
  min_zoom: number;
  max_zoom: number;
  key?: string;
}
