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
  | "basemap.manage"
  | "data.import"
  | "data.export"
  | "boundary.approve"
  | "checklist.edit"
  | "checklist.verify"
  | "checklist.template"
  | "field.package"
  | "field.sync"
  | "sync.resolve"
  | "relations.edit"
  | "standards.manage"
  | "permit.view"
  | "permit.process"
  | "permit.inspect"
  | "permit.decide"
  | "permit.settings"
  | "reports.view"
  | "enforcement.view"
  | "enforcement.open"
  | "enforcement.act"
  | "dataroom.view"
  | "dataroom.manage"
  | "dataroom.answer"
  | "revenue.view"
  | "revenue.manage"
  | "exchange.manage"
  | "data.sensitive";

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
  /** Personal data: hidden from roles without data.sensitive. */
  sensitive?: boolean;
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
  meta: {
    uuid: string;
    version: number;
    origin: string;
    verified: boolean;
    updated_at: string;
    /** Fields whose values this user's role may not see (they are left out of properties). */
    restricted?: string[];
  };
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

// --- Import and export (Phase 5) ---------------------------------------------------------

export interface InspectedField {
  name: string;
  suggested_name: string;
  type: FieldType;
}

export interface InspectedLayer {
  name: string;
  feature_count: number;
  geometry_types: Record<string, number>;
  has_z: boolean;
  fields: InspectedField[];
  crs: { found: boolean; epsg: number | null; confidence: number; name: string | null; wkt: string | null };
  encoding: string | null;
  cad_layers: string[];
}

export interface Inspection {
  format: string;
  layers: InspectedLayer[];
  crs_confirmation_required: boolean;
}

export interface ImportPlanItem {
  source: string;
  crs: string;
  crs_confirmed?: boolean;
  target_layer?: number;
  new_layer?: { name: string; domain: Domain; geometry_type: GeometryType };
  fields: { source: string; target: string; type?: FieldType }[];
  invalid_geometry?: "fix" | "skip" | "abort";
  duplicates?: "keep" | "skip";
  bad_values?: "blank" | "skip_feature";
  cad_layers?: string[];
  encoding?: string;
}

export interface ImportLayerReport {
  source: string;
  target_layer: number;
  target_name: string;
  imported: number;
  skipped: number;
  fixed_geometries: number;
  duplicates: number;
  blanked_values: number;
  z_dropped: number;
  operation: { name: string; accuracy_m: number | null } | null;
  problems: { row: number; message: string }[];
}

export type ExportFormat = "gpkg" | "shp" | "geojson" | "kml" | "kmz" | "dxf" | "dwg";

export interface DataJob {
  id: number;
  uuid: string;
  kind: "import" | "export";
  project: number;
  status: "uploaded" | "inspected" | "queued" | "running" | "done" | "failed";
  file_format: string;
  original_name: string;
  inspection: Inspection | Record<string, never>;
  plan: Record<string, unknown>;
  live_progress: { done: number; total: number; stage: string } | null;
  report: { layers?: ImportLayerReport[] } & Record<string, unknown>;
  error: string;
  result_name: string;
  download_url: string | null;
  created_at: string;
  finished_at: string | null;
}

// --- Editing and boundaries (Phase 6) ----------------------------------------------------

export interface HistoryEntry {
  audit_id: number;
  version: number | null;
  action: "INSERT" | "UPDATE" | "DELETE";
  at: string;
  user_email: string | null;
  changed_fields: string[];
  properties: Record<string, unknown> | null;
  geometry: GeoJSONGeometry | null;
}

export type BoundaryStatus = "draft" | "agreed" | "approved";
export type BoundaryMethod = "drawn" | "coordinates" | "traverse" | "import" | "gps";

export interface BoundaryReport {
  exists: boolean;
  feature?: number;
  status?: BoundaryStatus;
  valid?: boolean;
  invalid_reason?: string | null;
  vertices?: number;
  area_m2?: number;
  area_ha?: number;
  area_acres?: number;
  perimeter_m?: number;
  area_native?: number | null;
  perimeter_native?: number | null;
  native_units?: string;
  neighbours?: ({ project: number; name: string } & ({ kind: "overlap"; area_m2: number } | { kind: "gap"; distance_m: number }))[];
  district_boundary_loaded?: boolean;
  outside_district_m2?: number | null;
}

export interface TraverseLeg {
  bearing: string;
  distance: number;
}

export interface TraverseResult {
  stations: [number, number][];
  raw_end: [number, number];
  misclosure_e: number;
  misclosure_n: number;
  misclosure: number;
  perimeter: number;
  accuracy_ratio: number | null;
  adjusted: boolean;
  corrections: [number, number][];
  polygon: GeoJSONGeometry;
}

// --- Readiness checklist (Phase 7) ------------------------------------------------------

export type ChecklistGroup = "authority" | "planning_area" | "base_map" | "existing" | "people";
export type ChecklistKind = "document" | "layer" | "boundary";
export type ChecklistStatus = "not_started" | "in_progress" | "ready" | "verified";

export interface ChecklistRules {
  min_features?: number;
  min_coverage?: number;
  min_attributes?: number;
  max_age_days?: number;
  min_verified?: number;
  boundary_status?: BoundaryStatus;
  no_overlaps?: boolean;
  imagery_max_age_days?: number;
}

export interface LayerMetrics {
  layer: number;
  layer_name: string;
  feature_count: number;
  /** % of the planning area (grid cells) holding features; null without a boundary. */
  coverage: number | null;
  attributes: number | null;
  attribute_fields: string[];
  newest: string | null;
  age_days: number | null;
  verified: number | null;
}

export interface ImageryMetrics {
  imagery_count: number;
  undated: number;
  newest_capture: string | null;
  age_days: number | null;
  best_resolution_m: number | null;
}

export interface BoundaryMetrics {
  exists: boolean;
  status: BoundaryStatus | null;
  valid: boolean | null;
  area_ha: number | null;
  overlaps: number;
}

export interface ChecklistCheck {
  ok: boolean;
  label: string;
  problem: string | null;
}

export interface ChecklistAttachment {
  id: number;
  name: string;
  size: number;
  uploaded_at: string;
}

export interface ChecklistItem {
  id: number;
  group: ChecklistGroup;
  key: string;
  title: string;
  description: string;
  kind: ChecklistKind;
  domain: string;
  geometry_type: "" | "point" | "line" | "polygon";
  rules: ChecklistRules;
  status: ChecklistStatus;
  owner: number | null;
  owner_name: string | null;
  due_date: string | null;
  notes: string;
  linked_layer: number | null;
  attachments: ChecklistAttachment[];
  metrics: LayerMetrics | BoundaryMetrics | ImageryMetrics | null;
  checks: ChecklistCheck[];
  rules_met: boolean;
  complete: boolean;
  blockers: string[];
}

export interface ChecklistGroupProgress {
  group: ChecklistGroup;
  label: string;
  total: number;
  complete: number;
}

export interface Checklist {
  project: number;
  project_name: string;
  score: number;
  complete: number;
  total: number;
  groups: ChecklistGroupProgress[];
  items: ChecklistItem[];
  /** Totals from the relationship layer's last run; null until it has run. */
  baseline: (RelationsTotals & { at: string | null }) | null;
  blockers: { item: number; title: string; problem: string }[];
}

export interface ReadinessDashboard {
  score: number;
  projects: {
    project: number;
    name: string;
    status: string;
    score: number;
    complete: number;
    total: number;
    groups: ChecklistGroupProgress[];
    blockers: { item: number; title: string; problem: string }[];
  }[];
}

export interface TemplateItem {
  id: number;
  group: ChecklistGroup;
  key: string;
  title: string;
  description: string;
  kind: ChecklistKind;
  domain: string;
  geometry_type: string;
  rules: ChecklistRules;
  order: number;
}

export interface ChecklistTemplate {
  id: number | null;
  name: string | null;
  own: boolean;
  items: TemplateItem[];
}

// --- .spp project files (Phase 8) ---------------------------------------------------------

/** What opening a .spp file created. */
export interface SppReport {
  project: number;
  name: string;
  /** The file's project name, when a project with that name already existed here. */
  renamed_from: string | null;
  from_district: string | null;
  saved_at: string | null;
  saved_by: string | null;
  layers: number;
  features: number;
  history_entries: number;
  checklist_items: number;
  attachments: number;
  /** Features given new ids because the originals exist on this server. */
  new_feature_ids: number;
  crs_added: string[];
  basemaps_added: string[];
  basemaps_skipped: string[];
}

export interface SppKeys {
  configured: boolean;
  problem: string | null;
  keys: { key_id: string; fingerprint: string; active: boolean }[];
}

// --- Field sync (Phase 10) --------------------------------------------------------------

export interface FieldCapture {
  feature_version: number;
  method: "gps" | "gps_track" | "drawn" | "";
  accuracy_m: number | null;
  fix_time: string | null;
  readings: number | null;
  captured_at: string | null;
  captured_by: string | null;
  device_id: string;
  notes: string;
  received_at: string;
}

export interface FieldPhoto {
  uuid: string;
  feature: number;
  size: number;
  received: number;
  complete: boolean;
  latitude: number | null;
  longitude: number | null;
  accuracy_m: number | null;
  taken_at: string | null;
}

export type ConflictResolution = "keep_field" | "keep_office" | "merged";

export interface SyncConflict {
  id: number;
  project: number;
  feature: number;
  layer: number;
  layer_name: string;
  status: "open" | "resolved";
  resolution: ConflictResolution | "";
  submitted_by: string | null;
  created_at: string;
  base_version: number;
  server_version: number;
  resolved_by: string | null;
  resolved_at: string | null;
}

export interface SyncConflictDetail extends SyncConflict {
  schema: SchemaField[];
  office: { version: number; properties: Record<string, unknown>; geometry: GeoJSONGeometry | null };
  field: {
    properties: Record<string, unknown> | null;
    /** WGS 84; null when the device didn't change the shape. */
    geometry: GeoJSONGeometry | null;
    capture: Partial<FieldCapture>;
  };
}

export interface FieldTaskSummary {
  counts: { open: number; confirmed: number; corrected: number; not_found: number };
  tasks: { id: number; feature: number; feature_uuid: string; layer: number; status: "open" | "done"; outcome: string; item: string; notes: string; completed_by: string | null; completed_at: string | null }[];
}

// --- Drone and raster imagery (Phase 11) -----------------------------------------------------

export interface Imagery {
  id: number;
  project: number;
  name: string;
  kind: "ortho" | "dem";
  status: "queued" | "processing" | "ready" | "failed";
  error: string;
  original_name: string;
  capture_date: string | null;
  source: string;
  crs: string;
  width: number | null;
  height: number | null;
  bands: number | null;
  resolution_m: number | null;
  bounds: [number, number, number, number] | null;
  value_range: [number, number] | null;
  min_zoom: number;
  max_zoom: number;
  size_bytes: number;
  basemap: number | null;
  tile_url: string | null;
  created_at: string;
}

/** A GeoTIFF being uploaded in pieces. */
export interface ImageryUpload {
  id: string;
  file_name: string;
  size: number;
  received: number;
  /** The largest piece the server accepts, in bytes. */
  chunk_size: number;
}

/** What is said about an image when it is uploaded. */
export interface ImageryDetails {
  project: number;
  name?: string;
  kind: "ortho" | "dem";
  capture_date?: string;
  source?: string;
  crs?: string;
}

export interface ContourResult {
  layer: number;
  layer_name: string;
  contours: number;
  replaced: number;
  interval: number;
  converted_from: string | null;
}

// --- Relationship layer (Phase 12) ------------------------------------------------------------

export interface RelationsRegistry {
  roles: { code: string; label: string; domain: string; geometry: string[]; fields: { key: string; label: string; default: string }[] }[];
  link_types: { code: string; subject: string; verb: string; object: string; inverse: string; procedure: string }[];
  procedures: { code: string; does: string }[];
  defaults: Record<string, unknown>;
}

export interface LayerRoleRow {
  role: string;
  layer: number | null;
  config: Record<string, unknown>;
  /** A likely layer, offered while the role isn't set. */
  suggested: number | null;
}

export interface LinkSide {
  feature: number;
  layer: string;
  label: string;
}

export interface RelationshipLink {
  id: number;
  type: string;
  verb: string;
  inverse: string;
  subject: LinkSide;
  /** Null for a breach of a planning standard. */
  object: LinkSide | null;
  rule: string;
  method: "calculated" | "inferred" | "confirmed";
  status: "active" | "rejected";
  confidence: number;
  details: Record<string, unknown>;
  decided_by: string | null;
  decided_at: string | null;
  note: string;
  created_at: string;
}

export type LinkCounts = { found: number; added: number; updated: number; removed: number; kept: number };

export interface RelationsTotals {
  properties: number;
  in_flood_area?: number;
  without_road_access?: number;
  without_drain?: number;
  with_permit?: number;
  with_violations?: number;
  violations?: Record<string, number>;
  in_no_community?: number;
  population_served?: number;
  needs?: number;
  needs_addressed?: number;
  facilities?: number;
}

export interface RelationsSummary {
  project: RelationsTotals;
  communities: (RelationsTotals & { feature: number; name: string })[];
}

export interface RelationsRun {
  id: number;
  trigger: "manual" | "nightly" | "edit";
  status: "running" | "done" | "failed";
  started_at: string;
  finished_at: string | null;
  started_by: string | null;
  report: Record<string, { skipped?: string } | Record<string, LinkCounts | number>>;
  summary: RelationsSummary | Record<string, never>;
  error: string;
}

export interface DevelopmentStandard {
  id: number;
  zone: string;
  /** From any boundary. The three below apply to the street side, the sides and the back. */
  min_setback_m: number | null;
  front_setback_m: number | null;
  side_setback_m: number | null;
  rear_setback_m: number | null;
  min_floors: number | null;
  max_floors: number | null;
  max_coverage_pct: number | null;
  min_plot_m2: number | null;
  /** Along the street. */
  min_width_m: number | null;
  /** Words that, in a property's recorded use, suggest a prohibited use. */
  prohibited_uses: string[];
  permit_required: boolean;
  build_in_flood_area: boolean;
  /** "luspa-2025" while it is the national standard, unchanged. */
  source: string;
  notes: string;
  updated_at: string;
}

/** A zone of the national zoning standards (LUSPA, 2025). */
export interface NationalZone {
  code: string;
  name: string;
  group: string;
  colour: string;
  /** How the standards draw it where a plain colour isn't enough. */
  pattern: string;
  height: string;
  standard: Pick<
    DevelopmentStandard,
    "min_plot_m2" | "min_width_m" | "max_coverage_pct" | "min_floors" | "max_floors" | "front_setback_m" | "side_setback_m" | "rear_setback_m" | "prohibited_uses"
  > | null;
  permitted: string[];
  prohibited: string[];
}

export interface NationalZones {
  source: string;
  zones: NationalZone[];
}

export interface AdoptReport {
  added: string[];
  updated: string[];
  kept: string[];
}

export interface SchemeDeadline {
  /** The regulation that sets it. */
  rule: string;
  due_on: string;
  done_on?: string | null;
  overdue: boolean;
}

/** A project's entry in the register of zoning schemes. */
export interface ZoningScheme {
  id: number;
  project: number;
  name: string;
  status: "draft" | "approved" | "adopted";
  structure_plan_approved_on: string | null;
  approved_on: string | null;
  effective_on: string | null;
  sent_to_luspa_on: string | null;
  update_every_months: number;
  notes: string;
  deadlines: Partial<Record<"prepare" | "send_to_luspa" | "update", SchemeDeadline>>;
  updated_at: string;
}

// --- Permits (Phase 15) --------------------------------------------------------------------

export type PermitKind = "planning" | "development";
export type PermitStatus = "received" | "review" | "reported" | "granted" | "deferred" | "refused" | "issued" | "withdrawn";
export type PermitDecision = "grant" | "refuse" | "defer";

/** What the Regulations fix: categories, documents, deadlines, inspection points. */
export interface PermitRegistry {
  categories: { code: string; label: string; kind: PermitKind }[];
  requirements: { code: string; label: string; applies: string[]; rule: string }[];
  clocks: { code: string; label: string; days: number; rule: string }[];
  inspection_points: { code: string; label: string }[];
  considerations: string[];
  permit_valid_years: number;
}

/** A statutory step of an application: when it is due and whether it was done. */
export interface PermitClock {
  code: string;
  label: string;
  rule: string;
  days: number;
  due_on: string;
  done_on: string | null;
  /** Done, but after the due date. */
  late: boolean;
  /** Not done, and the due date has passed. */
  overdue: boolean;
}

export interface PermitCheck {
  code: string;
  label: string;
  outcome: "pass" | "fail" | "warn" | "unknown";
  detail: string;
}

export interface PermitChecks {
  ran_at: string;
  zone: { value: string | null; from: string; national: string | null; name: string | null } | null;
  standard: Record<string, unknown> | null;
  results: PermitCheck[];
  counts: Record<PermitCheck["outcome"], number>;
}

/** An application as it appears in a list. */
export interface PermitSummary {
  id: number;
  project: number;
  number: string;
  kind: PermitKind;
  category: string;
  category_label: string;
  status: PermitStatus;
  status_label: string;
  applicant_name: string;
  proposed_use: string;
  proposed_floors: number | null;
  /** The site's feature in the project's permits layer. */
  site: number | null;
  received_on: string;
  decided_on: string | null;
  issued_on: string | null;
  expires_on: string | null;
  expired: boolean;
  /** When the Certificate of Habitation was issued, for a completed development. */
  habitation_on: string | null;
  /** The first statutory step not done yet; null once the application is closed. */
  next_due: PermitClock | null;
  check_counts: Record<PermitCheck["outcome"], number> | null;
}

export interface PermitRequirement {
  code: string;
  label: string;
  rule: string;
  /** Asked for by the officer ("where applicable"), not required of every application. */
  asked_for: boolean;
  submitted: number;
}

export interface PermitApplication extends PermitSummary {
  /** "restricted" for roles that may not see personal data. */
  applicant_phone: string;
  applicant_email: string;
  applicant_address: string;
  description: string;
  acknowledged_on: string | null;
  inspected_on: string | null;
  reported_on: string | null;
  clocks: PermitClock[];
  /** The completed development's inspection and the 14 days for its Certificate of Habitation; null until inspected. */
  completion: { inspected_on: string; due_on: string; issued_on: string | null; late: boolean; overdue: boolean } | null;
  requirements: PermitRequirement[];
  extra_requirements: string[];
  documents: { id: number; requirement: string; name: string; size: number; uploaded_at: string }[];
  comments: { id: number; agency: string; body: string; objection: boolean; recorded_by: string | null; recorded_at: string }[];
  inspections: { id: number; purpose: "application" | "completion"; inspected_on: string; findings: Record<string, string>; summary: string; inspected_by: string | null }[];
  checks: PermitChecks | null;
  checked_at: string | null;
  recommendation: PermitDecision | "";
  report: string;
  reasons: string;
  conditions: string;
  processing_fee: string | null;
  processing_receipt: string;
  processing_paid_on: string | null;
  permit_fee: string | null;
  permit_receipt: string;
  permit_paid_on: string | null;
  /** Where the certificate's QR code leads; null until the permit is issued. */
  verify_url: string | null;
  /** Requests for review (r.62, Form 53) and appeals (r.63, Form 54) against the decision. */
  challenges: PermitChallenge[];
  events: { kind: string; on: string; note: string; by: string | null }[];
}

export interface PermitList {
  results: PermitSummary[];
  summary: { total: number; open: number; overdue: number; by_status: Record<PermitStatus, number> };
}

export interface NewPermit {
  project: number;
  kind: PermitKind;
  category: string;
  applicant_name: string;
  applicant_phone?: string;
  applicant_email?: string;
  applicant_address?: string;
  description?: string;
  proposed_use?: string;
  proposed_floors?: number | null;
  received_on?: string;
  extra_requirements?: string[];
  /** The site as a shape, in site_crs (default: the project's coordinate system). */
  site_geometry?: GeoJSONGeometry;
  site_crs?: string;
  /** Or: use this feature's shape (a parcel) as the site. */
  site_feature?: number;
}

/** A line of the Assembly's fee-fixing resolution. */
export interface PermitFee {
  id: number;
  stage: "processing" | "permit";
  kind: PermitKind;
  category: string;
  label: string;
  amount: string;
  updated_at: string;
}

/** What anyone holding a certificate is told about it. */
export interface PermitVerification {
  assembly: string;
  number: string;
  permit: string;
  for: string;
  applicant: string;
  locality: string;
  proposed_use: string;
  issued_on: string;
  expires_on: string;
  valid: boolean;
}

// --- The Public Data Room (Phase 16) -------------------------------------------------------

/** A district's data room, as its staff set it. */
export interface DataRoomSettings {
  /** The district's code: its public page is /public/<code>. */
  code: string;
  is_open: boolean;
  /** Whether the public register names the people permits were issued to. */
  show_applicants: boolean;
  welcome: string;
  contact: string;
  updated_at: string;
}

export interface Publication {
  id: number;
  project: number;
  project_name: string;
  permits: boolean;
  zoning: boolean;
  published_at: string;
}

export type RoomDocumentKind = "sdf" | "structure_plan" | "local_plan" | "zoning_scheme" | "notice" | "consultation" | "outsourced" | "other";

export interface RoomDocument {
  id: number;
  kind: RoomDocumentKind;
  kind_label: string;
  title: string;
  description: string;
  name: string;
  size: number;
  display_from: string;
  display_until: string | null;
  uploaded_at?: string;
}

export interface InformationRequest {
  id: number;
  reference: string;
  name: string;
  phone: string;
  email: string;
  subject: string;
  body: string;
  received_on: string;
  status: "open" | "answered" | "declined";
  answer: string;
  answered_on: string | null;
  answered_by: string | null;
  due_on: string;
  late: boolean;
  overdue: boolean;
}

export interface InformationRequests {
  answer_within_days: number;
  open: number;
  overdue: number;
  results: InformationRequest[];
}

/** What anyone sees of an Assembly's data room. */
export interface PublicRoom {
  code: string;
  assembly: string;
  welcome: string;
  contact: string;
  answer_within_days: number;
  fees: { label: string; stage: "processing" | "permit"; kind: PermitKind; amount: string }[];
  documents: RoomDocument[];
  zoning_schemes: { name: string; status: string; approved_on: string | null; effective_on: string | null; locality: string }[];
}

export interface RegisterEntry {
  number: string;
  permit: string;
  for: string;
  proposed_use: string;
  locality: string;
  /** Null unless the Assembly shows names. */
  applicant: string | null;
  status: string;
  received_on: string;
  decided_on: string | null;
  issued_on: string | null;
  expires_on: string | null;
  expired: boolean;
  /** The grounds, for a refused application. */
  reasons: string;
}

/** An enforcement notice served, as the public register shows it. */
export interface PublicNotice {
  case: string;
  notice: string;
  contravention: string;
  locality: string;
  served_on: string;
  comply_by: string | null;
  complied_on: string | null;
}

export interface PublicStatus {
  number: string;
  permit: string;
  status: string;
  received_on: string;
  decided_on: string | null;
  issued_on: string | null;
  next_step: { label: string; due_on: string } | null;
}

/** "What can I build here?" */
export type PublicZone =
  | { found: false; detail: string }
  | {
      found: true;
      zone: string;
      from: string;
      locality: string;
      code: string | null;
      name: string;
      colour: string | null;
      permitted: string[];
      prohibited: string[];
      standard: Pick<
        DevelopmentStandard,
        "min_setback_m" | "front_setback_m" | "side_setback_m" | "rear_setback_m" | "min_floors" | "max_floors" | "max_coverage_pct" | "min_plot_m2" | "min_width_m"
      > | null;
      note: string;
    };

// --- Enforcement (Phase 17) ----------------------------------------------------------------

export interface EnforcementRegistry {
  contraventions: { code: string; label: string; section: string }[];
  notices: { code: string; label: string; form: string; rule: string; dated: boolean }[];
  service_methods: { code: string; label: string }[];
  days: { enforcement_after: number; act_after: number; entry_notice: number; show_cause: number };
}

export type CaseStatus = "open" | "notice" | "rectified" | "enforced" | "dropped";

export interface EnforcementNotice {
  id: number;
  kind: string;
  label: string;
  /** The Schedule form it is served on, or "" where the Regulations give none. */
  form: string;
  rule: string;
  grounds: string;
  required: string;
  issued_on: string;
  comply_by: string | null;
  served_on: string | null;
  served_by: string;
  served_by_label: string;
  served_note: string;
  complied_on: string | null;
  /** What follows from the notice, by the Regulations' days. */
  dates: Partial<{
    enforcement_notice_due_on: string;
    overdue: boolean;
    assembly_may_act_from: string;
    entry_not_before: string;
    show_cause_by: string;
    past_comply_by: boolean;
  }>;
}

export interface CaseSummary {
  id: number;
  project: number;
  number: string;
  origin: "inspection" | "complaint" | "detection" | "check";
  origin_label: string;
  contravention: string;
  contravention_label: string;
  section: string;
  description: string;
  status: CaseStatus;
  status_label: string;
  feature: number | null;
  permit: number | null;
  permit_number: string | null;
  opened_on: string;
  closed_on: string | null;
  next_action: { label: string; due_on: string | null; overdue: boolean } | null;
}

export interface EnforcementCase extends CaseSummary {
  /** "restricted" for roles that may not see personal data. */
  owner_name: string;
  owner_address: string;
  owner_contact: string;
  outcome: string;
  cost: string | null;
  cost_recovered: string | null;
  opened_by: string | null;
  notices: EnforcementNotice[];
}

export interface CaseList {
  results: CaseSummary[];
  summary: { total: number; open: number; overdue: number };
}

export interface NewCase {
  project: number;
  origin?: CaseSummary["origin"];
  contravention: string;
  description?: string;
  feature?: number | null;
  permit?: number | null;
  owner_name?: string;
  owner_address?: string;
  owner_contact?: string;
  opened_on?: string;
}

/** One comparison of two orthophotos. */
export interface DetectionRun {
  id: number;
  before: string | null;
  after: string | null;
  /** The layer the changed places were put in. */
  layer: number | null;
  found: number;
  summary: { permitted: number; existing: number; new: number };
  kinds: { permitted: string; existing: string; new: string };
  at: string;
  started_by: string | null;
}

// --- The district's statutory deadlines (reports) ------------------------------------------

export interface LateRow {
  id?: number;
  project: number;
  number?: string;
  scheme?: string;
  step?: string;
  duty?: string;
  rule?: string;
  due_on: string | null;
  days_late?: number;
}

export interface Compliance {
  as_of: string;
  /** Every duty past its date, across permits, requests, enforcement and zoning. */
  overdue: number;
  permits: {
    open: number;
    overdue: number;
    overdue_by_step: Record<"acknowledge" | "inspect" | "report" | "issue", number>;
    received_this_year: number;
    decided_this_year: number;
    decided_within_limit_pct: number | null;
    average_days_to_decision: number | null;
    limit_days: number;
    late: LateRow[];
  };
  requests: { open: number; overdue: number; answered_this_year: number; answered_within_limit_pct: number | null; limit_days: number };
  enforcement: { open: number; overdue: number; late: LateRow[] };
  /** Re-zoning, change of use, subdivision and consolidation (r.33, r.34, r.54). */
  land: { open: number; overdue: number; late: LateRow[] };
  zoning: { schemes: number; overdue: number; late: LateRow[] };
  dataroom: { is_open: boolean; published_projects: number; documents_on_display: number };
  week_ahead: LateRow[];
}

// --- Street addressing (Phase 20) -----------------------------------------------------------

export type AddressingMethod = "decametric" | "metric" | "sequential";

export interface AddressRow {
  property: number;
  label: string;
  street: number;
  street_name: string;
  street_code: string;
  side: "left" | "right";
  /** Metres from the start of the street. */
  distance_m: number;
  off_street_m: number;
  number: string;
  address: string;
  /** The number the property has on the map now ("" if none). */
  current: string;
}

/** Street codes and property numbers as they would be: nothing is saved until applied. */
export interface AddressProposal {
  method: AddressingMethod;
  method_label: string;
  odd_side: "left" | "right";
  start_near: [number, number] | null;
  streets: number;
  streets_without_a_name: number;
  new_street_codes: { street: number; code: string }[];
  properties: number;
  numbered: number;
  /** Too far from any street to be numbered on it; null when there are too many to count in one go. */
  without_a_street: number | null;
  /** Properties whose number would change. */
  changes: number;
  truncated: boolean;
  /** The first few hundred rows; the schedule (CSV) has them all. */
  rows: AddressRow[];
  methods: Record<AddressingMethod, string>;
}

export interface AddressingOptions {
  method?: AddressingMethod;
  odd_side?: "left" | "right";
  lon?: number;
  lat?: number;
}

// --- Re-zoning, change of use, subdivision and consolidation (Phase 18) ---------------------

export type LandKind = "rezoning" | "change_of_use" | "subdivision" | "consolidation";
export type LandStatus = "received" | "deferred" | "approved" | "refused" | "withdrawn";

export interface LandRegistry {
  kinds: {
    code: LandKind;
    label: string;
    form: string;
    rule: string;
    comment_days: number;
    decide_days: number;
    decide_rule: string;
    steps: { code: string; label: string; rule: string; days: number | null; after: string; when: string }[];
  }[];
  grounds: { code: string; label: string }[];
  circumstances: { code: string; label: string }[];
  use_tests: { code: string; label: string; rule: string }[];
  comment_kinds: { code: string; label: string }[];
  deferred_decision_days: number;
}

/** One step of an application: when it is due (where the Regulations set a time) and when it was done. */
export interface LandClock {
  code: string;
  label: string;
  rule: string;
  days: number | null;
  due_on: string | null;
  done_on: string | null;
  note: string;
  late: boolean;
  overdue: boolean;
}

export interface LandSummary {
  id: number;
  project: number;
  number: string;
  kind: LandKind;
  kind_label: string;
  applicant_name: string;
  summary: string;
  status: LandStatus;
  status_label: string;
  received_on: string;
  decided_on: string | null;
  /** The last day for the public's comments, once the application is on display. */
  comments_close_on: string | null;
  next_step: LandClock | null;
}

export interface LandComment {
  id: number;
  kind: string;
  kind_label: string;
  /** "restricted" for roles that may not see personal data. */
  name: string;
  contact: string;
  text: string;
  received_on: string;
  response: string;
  responded_on: string | null;
}

export interface LandApplication extends LandSummary {
  form: string;
  rule: string;
  applicant_phone: string;
  applicant_email: string;
  applicant_address: string;
  description: string;
  parcels: { id: number; label: string; zone: string; area_m2: number }[];
  /** The parcels that touch the land: their owners are given notice (r.33(8)). */
  abutting: { id: number; label: string; owner: string; area_m2: number }[];
  current_zone: string;
  proposed_zone: string;
  ground: string;
  circumstance: string;
  current_use: string;
  proposed_use: string;
  lots: number | null;
  zone: { value: string; national: string | null; name: string | null; prohibited_uses: string[] };
  assessment: Record<string, { met: boolean; note: string }>;
  clocks: LandClock[];
  comment_rule: string;
  comments: LandComment[];
  deferred_on: string | null;
  defer_reason: string;
  conditions: string;
  reasons: string;
  applied_on: string | null;
  papers: { code: string; label: string }[];
}

export interface NewLandApplication {
  project: number;
  kind: LandKind;
  applicant_name: string;
  applicant_phone?: string;
  applicant_address?: string;
  description?: string;
  parcels: number[];
  proposed_zone?: string;
  ground?: string;
  circumstance?: string;
  current_use?: string;
  proposed_use?: string;
  lots?: number;
  received_on?: string;
}

export interface PublicLandApplication {
  number: string;
  kind: string;
  proposal: string;
  locality: string;
  received_on: string;
  comments_close_on: string | null;
  status: string;
  decided_on: string | null;
}

// --- Making a local plan, and its consultation (Phase 19) -----------------------------------

export interface PlanClock {
  code: string;
  label: string;
  rule: string;
  /** The Schedule form of the notice, if the step has one. */
  form: string;
  /** "12 months", "7 days", or "" where the Regulations set no time. */
  limit: string;
  /** Recorded only by those who may decide. */
  decision: boolean;
  due_on: string | null;
  done_on: string | null;
  note: string;
  late: boolean;
  overdue: boolean;
}

export interface PlanConsultation {
  id: number;
  stage: string;
  stage_label: string;
  held_on: string;
  venue: string;
  groups: string;
  attendance: number | null;
  issues: string;
  outcome: string;
  /** When the minutes went on display in the Public Data Room (r.65(3)). */
  displayed_on: string | null;
}

export interface PlanComment {
  id: number;
  /** "restricted" for roles that may not see personal data. */
  name: string;
  contact: string;
  topic: string;
  topic_label: string;
  text: string;
  received_on: string;
  /** Sent in through the Public Data Room, not recorded at the office. */
  online: boolean;
  response: string;
  responded_on: string | null;
}

export interface PlanProcess {
  project: number;
  origin: "committee" | "applicant";
  origin_label: string;
  prepared_by: string;
  structure_plan_on: string | null;
  application_on: string | null;
  conditions: string;
  valid_until: string | null;
  clocks: PlanClock[];
  next_step: PlanClock | null;
  comment_days: number;
  comment_rule: string;
  comments_close_on: string | null;
  comments_open: boolean;
  /** Each item a local plan must specify (r.24(1)), and whether this plan covers it. */
  content: { code: string; label: string; covered: boolean; note: string }[];
  content_rule: string;
  content_covered: number;
  possible_conditions: string[];
  stages: { code: string; label: string }[];
  consultations: PlanConsultation[];
  comments: PlanComment[];
  comments_unanswered: number;
  papers: { code: string; label: string }[];
}

export interface PlanSettings {
  origin?: "committee" | "applicant";
  prepared_by?: string;
  structure_plan_on?: string | null;
  application_on?: string | null;
  conditions?: string;
  valid_until?: string | null;
}

export interface NewConsultation {
  stage: string;
  held_on: string;
  venue: string;
  groups?: string;
  attendance?: number | null;
  issues: string;
  outcome?: string;
}

export interface PublicPlan {
  project: number;
  name: string;
  locality: string;
  commenced_on: string | null;
  draft_on_display_from: string | null;
  comments_close_on: string | null;
  comments_open: boolean;
  approved_on: string | null;
  consultations: { stage: string; held_on: string; venue: string; attendance: number | null; issues: string; outcome: string }[];
}

// --- Property register, rates and betterment (Phase 21) -------------------------------------

export type PropertyUse = "residential" | "commercial" | "industrial" | "mixed" | "institutional" | "vacant" | "other";
export type RateStatus = "never_billed" | "unpaid" | "paid";

export interface RateBill {
  id: number;
  year: number;
  reference: string;
  amount: string;
  paid: string;
  owing: string;
  issued_on: string;
  last_paid_on: string | null;
  source: "platform" | "revenue";
}

export interface RegisterProperty {
  id: number;
  project: number;
  feature: number | null;
  number: string;
  address: string;
  use: PropertyUse;
  use_label: string;
  /** "restricted" for roles that may not see personal data. */
  owner_name: string;
  owner_contact: string;
  valuation_ref: string;
  rateable_value: string | null;
  valued_on: string | null;
  revenue_ref: string;
  status: RateStatus;
  bills: RateBill[];
}

export interface RegisterSummary {
  properties: number;
  valued: number;
  by_status: Record<RateStatus, number>;
  billed: string;
  paid: string;
  owing: string;
  collected_pct: number | null;
}

export interface RateBand {
  id: number;
  year: number;
  use: PropertyUse;
  impost: string;
  minimum: string;
  flat: string | null;
}

/** What an import or a billing run did: rows that matched, and those that didn't. */
export interface RegisterImport {
  rows: number;
  matched: number;
  unmatched: { row: number; reference: string; reason?: string }[];
  unmatched_count: number;
}

export interface BettermentCharge {
  id: number;
  property: number;
  number: string;
  address: string;
  owner_name: string;
  distance_m: string;
  increase: string | null;
  amount: string | null;
  served_on: string | null;
  paid: string;
  paid_on: string | null;
}

export interface BettermentScheme {
  id: number;
  project: number;
  name: string;
  works: string;
  works_feature: number | null;
  reach_m: string;
  completed_on: string;
  basis: "sum" | "rate";
  basis_label: string;
  amount: string;
  charges_count: number;
  total: string;
  collected: string;
  clocks: {
    serve_by: string;
    rule: string;
    unserved: number;
    served_late: number;
    overdue: boolean;
    published: { code: string; label: string; on: string | null }[];
  };
  charges?: BettermentCharge[];
  found?: { found: number; added: number };
}

// --- Returns and national data exchange (Phase 22) ------------------------------------------

export interface DistrictReturn {
  district: { code: string; name: string };
  period: { label: string; from: string; to: string };
  permits: {
    received: number;
    received_by_kind: { development: number; planning: number };
    received_by_category: { category: string; count: number }[];
    decided: number;
    granted: number;
    refused: number;
    issued: number;
    decided_within_limit_pct: number | null;
    average_days_to_decision: number | null;
    limit_days: number;
  };
  land: { kind: string; received: number; approved: number; refused: number }[];
  enforcement: {
    cases_opened: number;
    opened_by_contravention: { contravention: string; count: number }[];
    notices_served: number;
    notices_by_kind: { notice: string; form: string; count: number }[];
    cases_closed: number;
    closed_by_outcome: { rectified: number; enforced: number; dropped: number };
    cost_recovered: string;
  };
  plans: { commenced: string[]; drafts_on_display: string[]; approved: string[]; consultations_held: number; comments_received: number };
  data_room: { requests_received: number; answered: number; answered_within_limit_pct: number | null };
  revenue: { bills_issued: number; billed: string; paid_on_bills_with_payments: string; betterment_schemes_completed: number };
}

export interface ExchangeKey {
  id: number;
  name: string;
  prefix: string;
  scopes: string[];
  created_at: string;
  created_by: string | null;
  last_used_at: string | null;
  uses: number;
  revoked_at: string | null;
  /** Only when just made: the whole key, shown once. */
  key?: string;
}

export interface PermitChallenge {
  id: number;
  kind: "review" | "appeal";
  kind_label: string;
  form: string;
  rule: string;
  body: string;
  body_label: string;
  lodged_on: string;
  grounds: string;
  decided_on: string | null;
  outcome: "" | "upheld" | "varied" | "overturned" | "withdrawn";
  outcome_label: string;
  decision: string;
  clock: { decide_by: string; overdue: boolean; late: boolean; lodge_by: string | null; lodged_late: boolean };
}

// --- Planning committees and their meetings -------------------------------------------------

export type CommitteeKind = "dspc" | "tsc";

export interface CommitteeMember {
  name: string;
  office: string;
}

export interface Committees {
  committees: { kind: CommitteeKind; label: string; members: CommitteeMember[] }[];
  offices: { code: string; label: string }[];
  outcomes: { code: string; label: string }[];
}

export interface AgendaItem {
  type: "permit" | "land" | "plan" | "other";
  ref: number | null;
  /** The project an application or plan belongs to. */
  project: number | null;
  title: string;
  outcome: string;
  minute: string;
}

export interface MeetingSummary {
  id: number;
  committee: CommitteeKind;
  committee_label: string;
  held_on: string;
  venue: string;
  items: number;
  considered: number;
  notice: { serve_by: string; served_on: string | null; late: boolean; overdue: boolean; rule: string };
  quorum: { present: number; needed: number; missing_offices: string[]; met: boolean; rule: string };
}

export interface Meeting extends MeetingSummary {
  members: CommitteeMember[];
  attendance: string[];
  agenda: AgendaItem[];
  notes: string;
}

/** A planning area's facilities against the national planning standards (LUSPA 2025). */
export interface FacilityCheck {
  population: { value: number | null; source: string; estimate?: boolean };
  facilities_layer: { id: number; name: string; type_field: string } | null;
  homes?: number;
  results: {
    code: string;
    label: string;
    section: string;
    per: number | null;
    have: number;
    need: number | null;
    short: number | null;
    walk_m: number | null;
    /** Buildings farther than the walking distance from the nearest one. */
    beyond: number | null;
    acres_need: number | null;
    acres_have: number | null;
    status: "met" | "short" | "unknown";
  }[];
  unclassified: { type: string; count: number }[];
  source: string;
}
