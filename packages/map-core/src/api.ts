// Typed client for the backend API, shared by the web and mobile apps.

import { memoryTokenStore, type TokenStore } from "./tokens";
import type {
  AuditEntry,
  BoundaryMethod,
  BoundaryReport,
  BoundaryStatus,
  HistoryEntry,
  TraverseLeg,
  TraverseResult,
  DataJob,
  ExportFormat,
  ImportPlanItem,
  Basemap,
  BasemapConfig,
  BasemapPreset,
  CoordinateSystem,
  CrsDefaults,
  CrsOperation,
  DefinitionPreview,
  FeaturePage,
  GeoJSONGeometry,
  Layer,
  MapFeature,
  Position,
  Project,
  AuditFilters,
  District,
  DistrictKind,
  LoginResponse,
  Me,
  Member,
  Page,
  Region,
  Role,
  Tokens,
  User,
  Checklist,
  ChecklistItem,
  ChecklistStatus,
  ChecklistTemplate,
  ReadinessDashboard,
  TemplateItem,
  SppKeys,
  SppReport,
  ConflictResolution,
  FieldCapture,
  FieldPhoto,
  FieldTaskSummary,
  SyncConflict,
  SyncConflictDetail,
  ContourResult,
  Imagery,
  ImageryDetails,
  ImageryUpload,
  DevelopmentStandard,
  AddressingOptions,
  AddressProposal,
  AdoptReport,
  Compliance,
  CaseList,
  DetectionRun,
  EnforcementCase,
  EnforcementRegistry,
  LandApplication,
  LandRegistry,
  LandSummary,
  NewLandApplication,
  PublicLandApplication,
  NewConsultation,
  PlanProcess,
  PlanSettings,
  PublicPlan,
  BettermentCharge,
  BettermentScheme,
  PropertyUse,
  RateBand,
  RegisterImport,
  RegisterProperty,
  RegisterSummary,
  DistrictReturn,
  ExchangeKey,
  NewCase,
  DataRoomSettings,
  InformationRequest,
  InformationRequests,
  Publication,
  PublicNotice,
  PublicRoom,
  PublicStatus,
  PublicZone,
  RegisterEntry,
  RoomDocument,
  RoomDocumentKind,
  NewPermit,
  PermitApplication,
  PermitDecision,
  PermitFee,
  PermitList,
  PermitRegistry,
  PermitVerification,
  NationalZones,
  ZoningScheme,
  LayerRoleRow,
  RelationsRegistry,
  RelationsRun,
  RelationsSummary,
  RelationshipLink,
} from "./types";

export interface ServiceStatus {
  ok: boolean;
  error?: string;
}

export interface HealthReport {
  ok: boolean;
  database: ServiceStatus & { postgis?: string; proj?: string };
  gdal: ServiceStatus & { version?: string; missing_drivers?: string[] };
  redis: ServiceStatus;
}

/** A failed API call. `fields` holds per-field validation messages (HTTP 400). */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly fields: Record<string, string[]> = {},
    /** The parsed response body, e.g. the current feature on 409 Conflict. */
    readonly body: unknown = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export interface ApiClientOptions {
  baseUrl?: string;
  fetch?: typeof fetch;
  tokens?: TokenStore;
  /** Active district, sent as X-District-ID on every request. */
  getDistrictId?: () => number | null;
  /** Called when the refresh token is rejected: the user must sign in again. */
  onSessionExpired?: () => void;
  /** Milliseconds to wait before retry number `attempt` of a dropped upload piece. */
  retryDelay?: (attempt: number) => number;
}

/** How often a piece of an upload is retried after the connection drops. */
const UPLOAD_RETRIES = 8;

type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

function toMessages(value: unknown): string[] {
  if (Array.isArray(value)) return value.map(String);
  if (typeof value === "string") return [value];
  return [];
}

async function toApiError(response: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    // not JSON
  }
  if (body && typeof body === "object" && !Array.isArray(body)) {
    const record = body as Record<string, unknown>;
    if (typeof record.detail === "string") return new ApiError(record.detail, response.status, {}, body);
    const fields: Record<string, string[]> = {};
    for (const [key, value] of Object.entries(record)) fields[key] = toMessages(value);
    const first = fields.non_field_errors?.[0] ?? Object.values(fields)[0]?.[0];
    return new ApiError(first ?? `Request failed (HTTP ${response.status})`, response.status, fields, body);
  }
  if (Array.isArray(body)) {
    return new ApiError(toMessages(body)[0] ?? `Request failed (HTTP ${response.status})`, response.status);
  }
  return new ApiError(`Request failed (HTTP ${response.status})`, response.status);
}

function query(params: object): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export function createApiClient(options: ApiClientOptions = {}) {
  const root = (options.baseUrl ?? "").replace(/\/$/, "");
  // Look fetch up at call time so tests can replace the global.
  const doFetch: typeof fetch = (...args) => (options.fetch ?? fetch)(...args);
  const tokens = options.tokens ?? memoryTokenStore();
  let refreshing: Promise<boolean> | null = null;

  function headers(json: boolean): Headers {
    const h = new Headers();
    if (json) h.set("Content-Type", "application/json");
    const access = tokens.get()?.access;
    if (access) h.set("Authorization", `Bearer ${access}`);
    const districtId = options.getDistrictId?.();
    if (districtId) h.set("X-District-ID", String(districtId));
    return h;
  }

  // Concurrent 401s share one refresh request.
  function refreshTokens(): Promise<boolean> {
    refreshing ??= (async () => {
      const refresh = tokens.get()?.refresh;
      if (!refresh) return false;
      const response = await doFetch(`${root}/api/auth/refresh/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh }),
      });
      if (!response.ok) return false;
      tokens.set((await response.json()) as Tokens);
      return true;
    })().finally(() => {
      refreshing = null;
    });
    return refreshing;
  }

  const retryDelay = options.retryDelay ?? ((attempt: number) => Math.min(30_000, 1000 * 2 ** attempt));

  /** Raw bytes, authenticated (a piece of an upload). Network errors are thrown. */
  async function sendBytes(method: Method, path: string, body: Blob): Promise<Response> {
    const send = () => {
      const h = headers(false);
      h.set("Content-Type", "application/octet-stream");
      return doFetch(`${root}${path}`, { method, headers: h, body });
    };
    let response = await send();
    if (response.status === 401 && tokens.get() && (await refreshTokens())) response = await send();
    return response;
  }

  /** A public read: no token is sent. With `orNull`, a 404 is "nothing there". */
  function open<T>(path: string): Promise<T>;
  function open<T>(path: string, orNull: true): Promise<T | null>;
  async function open<T>(path: string, orNull = false): Promise<T | null> {
    const response = await doFetch(`${root}${path}`);
    if (orNull && response.status === 404) return null;
    if (!response.ok) throw await toApiError(response);
    return (await response.json()) as T;
  }

  /** An authenticated file download. */
  async function blob(path: string): Promise<Blob> {
    const send = () => doFetch(`${root}${path}`, { headers: headers(false) });
    let response = await send();
    if (response.status === 401 && tokens.get() && (await refreshTokens())) response = await send();
    if (!response.ok) throw await toApiError(response);
    return response.blob();
  }

  async function request<T>(method: Method, path: string, body?: unknown, retry = true): Promise<T> {
    const response = await doFetch(`${root}${path}`, {
      method,
      headers: headers(body !== undefined),
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (response.status === 401 && retry && tokens.get()) {
      if (await refreshTokens()) return request<T>(method, path, body, false);
      tokens.clear();
      options.onSessionExpired?.();
    }
    if (!response.ok) throw await toApiError(response);
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  }

  return {
    tokens,

    // A failing service returns 503 with the same body, which callers still
    // want to show, so only non-JSON responses are treated as errors.
    async getHealth(): Promise<HealthReport> {
      const response = await doFetch(`${root}/api/health/`);
      const type = response.headers.get("content-type") ?? "";
      if (!type.includes("application/json")) {
        throw new ApiError(`Health check failed (HTTP ${response.status})`, response.status);
      }
      return (await response.json()) as HealthReport;
    },

    // --- Session -------------------------------------------------------------
    async login(email: string, password: string): Promise<Me> {
      const result = await request<LoginResponse>("POST", "/api/auth/login/", { email, password }, false);
      tokens.set({ access: result.access, refresh: result.refresh });
      return result.user;
    },
    async logout(): Promise<void> {
      const refresh = tokens.get()?.refresh;
      tokens.clear();
      if (refresh) {
        // Best effort: the session is over locally either way.
        await request("POST", "/api/auth/logout/", { refresh }, false).catch(() => undefined);
      }
    },
    me: () => request<Me>("GET", "/api/auth/me/"),
    changePassword: (current_password: string, new_password: string) =>
      request<void>("POST", "/api/auth/password/change/", { current_password, new_password }),
    requestPasswordReset: (email: string) =>
      request<void>("POST", "/api/auth/password/reset/", { email }, false),
    confirmPasswordReset: (uid: string, token: string, new_password: string) =>
      request<void>("POST", "/api/auth/password/reset/confirm/", { uid, token, new_password }, false),

    // --- Regions and districts (writes: system admin) --------------------------
    listRegions: () => request<Region[]>("GET", "/api/regions/"),
    createRegion: (data: Omit<Region, "id">) => request<Region>("POST", "/api/regions/", data),
    listDistricts: () => request<District[]>("GET", "/api/districts/"),
    createDistrict: (data: { name: string; code: string; kind: DistrictKind; region: number }) =>
      request<District>("POST", "/api/districts/", data),
    updateDistrict: (id: number, data: Partial<Pick<District, "name" | "code" | "kind" | "is_active">>) =>
      request<District>("PATCH", `/api/districts/${id}/`, data),

    // --- Users (system admin) --------------------------------------------------
    listUsers: (params: { search?: string; page?: number } = {}) =>
      request<Page<User>>("GET", `/api/users/${query(params)}`),
    createUser: (data: { email: string; first_name?: string; last_name?: string; is_system_admin?: boolean }) =>
      request<User>("POST", "/api/users/", data),
    updateUser: (id: number, data: Partial<Pick<User, "first_name" | "last_name" | "is_active" | "is_system_admin">>) =>
      request<User>("PATCH", `/api/users/${id}/`, data),
    unlockUser: (id: number) => request<User>("POST", `/api/users/${id}/unlock/`),
    sendPasswordReset: (id: number) => request<void>("POST", `/api/users/${id}/send-password-reset/`),

    // --- Members of the active district -----------------------------------------
    listMembers: (page = 1) => request<Page<Member>>("GET", `/api/memberships/${query({ page })}`),
    addMember: (data: { email: string; role: Role; first_name?: string; last_name?: string }) =>
      request<Member>("POST", "/api/memberships/", data),
    updateMember: (id: number, data: Partial<Pick<Member, "role" | "is_active">>) =>
      request<Member>("PATCH", `/api/memberships/${id}/`, data),
    removeMember: (id: number) => request<void>("DELETE", `/api/memberships/${id}/`),

    // --- Coordinate reference systems ---------------------------------------------
    listCrs: (params: { search?: string; include_inactive?: boolean } = {}) =>
      request<CoordinateSystem[]>("GET", `/api/crs/systems/${query(params)}`),
    addCrs: (data: { definition: string; name?: string; notes?: string; scope?: "district" | "global" }) =>
      request<CoordinateSystem>("POST", "/api/crs/systems/", data),
    updateCrs: (id: number, data: Partial<Pick<CoordinateSystem, "name" | "notes" | "is_active">>) =>
      request<CoordinateSystem>("PATCH", `/api/crs/systems/${id}/`, data),
    validateCrs: (definition: string) => request<DefinitionPreview>("POST", "/api/crs/validate/", { definition }),
    crsDefaults: () => request<CrsDefaults>("GET", "/api/crs/defaults/"),
    setSystemDefaultCrs: (crs: number) => request<void>("PUT", "/api/crs/defaults/system/", { crs }),
    setDistrictDefaultCrs: (crs: number | null) => request<void>("PUT", "/api/crs/defaults/district/", { crs }),
    setMyDefaultCrs: (crs: number | null) => request<void>("PUT", "/api/crs/defaults/me/", { crs }),
    transformPoints: (from_crs: string, to_crs: string, points: Position[]) =>
      request<{ points: Position[]; operation: CrsOperation }>("POST", "/api/crs/transform/", {
        from_crs,
        to_crs,
        points,
      }),
    crsOperations: (from_crs: string, to_crs: string) =>
      request<{ current: CrsOperation; candidates: CrsOperation[] }>(
        "GET",
        `/api/crs/operations/${query({ from_crs, to_crs })}`,
      ),
    pinCrsOperation: (from_crs: string, to_crs: string, pipeline: string) =>
      request<void>("PUT", "/api/crs/operations/", { from_crs, to_crs, pipeline }),
    unpinCrsOperation: (from_crs: string, to_crs: string) =>
      request<void>("DELETE", `/api/crs/operations/${query({ from_crs, to_crs })}`),

    // --- Projects, layers, features ----------------------------------------------
    listProjects: (params: { include_archived?: boolean; page?: number } = {}) =>
      request<Page<Project>>("GET", `/api/projects/${query(params)}`),
    getProject: (id: number) => request<Project>("GET", `/api/projects/${id}/`),
    createProject: (data: { name: string; community?: string; description?: string; crs?: number }) =>
      request<Project>("POST", "/api/projects/", data),
    updateProject: (id: number, data: Partial<Pick<Project, "name" | "community" | "description" | "status">>) =>
      request<Project>("PATCH", `/api/projects/${id}/`, data),
    archiveProject: (id: number) => request<void>("DELETE", `/api/projects/${id}/`),
    setLayerOrder: (projectId: number, layerIds: number[]) =>
      request<void>("POST", `/api/projects/${projectId}/layer-order/`, { layer_ids: layerIds }),

    listLayers: (projectId: number) => request<Layer[]>("GET", `/api/layers/${query({ project: projectId })}`),
    createLayer: (data: Partial<Layer> & Pick<Layer, "project" | "name" | "geometry_type">) =>
      request<Layer>("POST", "/api/layers/", data),
    /** Removing schema fields that hold values needs them listed in confirmDrop. */
    updateLayer: (id: number, data: Partial<Layer>, confirmDrop: string[] = []) =>
      request<Layer>(
        "PATCH",
        `/api/layers/${id}/${query({ confirm_drop: confirmDrop.join(",") })}`,
        data,
      ),
    deleteLayer: (id: number) => request<void>("DELETE", `/api/layers/${id}/`),
    layerExtent: (id: number) =>
      request<{ native: number[] | null; wgs84: number[] | null }>("GET", `/api/layers/${id}/extent/`),
    listFeatures: (
      layerId: number,
      params: { geometry?: "wgs84" | "native"; bbox?: string; limit?: number; offset?: number } = {},
    ) => request<FeaturePage>("GET", `/api/layers/${layerId}/features/${query(params)}`),
    createFeature: (
      layerId: number,
      data: { geometry?: GeoJSONGeometry | null; geometry_crs?: string; properties?: Record<string, unknown> },
    ) =>
      request<MapFeature>("POST", `/api/layers/${layerId}/features/`, data),
    /** 409 means someone else saved first; the error carries the current feature. */
    updateFeature: (
      id: number,
      data: {
        version: number;
        geometry?: GeoJSONGeometry | null;
        geometry_crs?: string;
        properties?: Record<string, unknown>;
      },
    ) => request<MapFeature>("PATCH", `/api/features/${id}/`, data),
    /** One feature, geometry in the layer's native CRS (exact coordinates). */
    getFeature: (id: number) => request<MapFeature>("GET", `/api/features/${id}/`),
    deleteFeature: (id: number) => request<void>("DELETE", `/api/features/${id}/`),
    /** Vector tile bytes (null when the tile is empty), with auth and district headers. */
    async fetchTile(layerId: number, z: number, x: number, y: number): Promise<ArrayBuffer | null> {
      const path = `/api/layers/${layerId}/tiles/${z}/${x}/${y}.pbf`;
      let response = await doFetch(`${root}${path}`, { headers: headers(false) });
      if (response.status === 401 && tokens.get() && (await refreshTokens())) {
        response = await doFetch(`${root}${path}`, { headers: headers(false) });
      }
      if (response.status === 204) return null;
      if (!response.ok) throw await toApiError(response);
      return response.arrayBuffer();
    },

    // --- Editing and boundaries -------------------------------------------------------
    featureHistory: (id: number) => request<HistoryEntry[]>("GET", `/api/features/${id}/history/`),
    restoreFeature: (id: number, audit_id: number, version: number) =>
      request<MapFeature>("POST", `/api/features/${id}/restore/`, { audit_id, version }),
    splitFeature: (id: number, version: number, blade: GeoJSONGeometry, blade_crs?: string) =>
      request<{ features: MapFeature[] }>("POST", `/api/features/${id}/split/`, { version, blade, blade_crs }),
    mergeFeatures: (feature_ids: number[], keep: number) =>
      request<MapFeature>("POST", "/api/features/merge/", { feature_ids, keep }),
    boundaryReport: (projectId: number) => request<BoundaryReport>("GET", `/api/projects/${projectId}/boundary/`),
    setBoundary: (projectId: number, geometry: GeoJSONGeometry, method: BoundaryMethod, geometry_crs?: string) =>
      request<BoundaryReport>("PUT", `/api/projects/${projectId}/boundary/`, { geometry, method, geometry_crs }),
    setBoundaryStatus: (projectId: number, status: BoundaryStatus) =>
      request<BoundaryReport>("POST", `/api/projects/${projectId}/boundary-status/`, { status }),
    computeTraverse: (data: { start: [number, number]; legs: TraverseLeg[]; adjust: boolean; scale_factor?: number }) =>
      request<TraverseResult>("POST", "/api/geometry/traverse/", data),

    // --- Basemaps --------------------------------------------------------------------
    listBasemaps: (params: { include_inactive?: boolean } = {}) =>
      request<Basemap[]>("GET", `/api/basemaps/${query(params)}`),
    addBasemapPreset: (preset: BasemapPreset, api_key = "", scope: "district" | "global" = "district") =>
      request<Basemap>("POST", "/api/basemaps/presets/", { preset, api_key, scope }),
    createBasemap: (data: Partial<Basemap> & { api_key?: string; scope?: "district" | "global" }) =>
      request<Basemap>("POST", "/api/basemaps/", data),
    updateBasemap: (id: number, data: Partial<Basemap> & { api_key?: string }) =>
      request<Basemap>("PATCH", `/api/basemaps/${id}/`, data),
    /** 400 with a plain message when the key is missing or rejected. */
    basemapConfig: (id: number) => request<BasemapConfig>("GET", `/api/basemaps/${id}/client-config/`),

    // --- Import and export ----------------------------------------------------------
    /** Uploads a file for import; the job comes back inspected (or a 400 explaining why not). */
    async uploadImport(projectId: number, file: File, encoding?: string): Promise<DataJob> {
      const form = new FormData();
      form.set("project", String(projectId));
      form.set("file", file);
      if (encoding) form.set("encoding", encoding);
      const send = () => doFetch(`${root}/api/transfer/jobs/imports/`, { method: "POST", headers: headers(false), body: form });
      let response = await send();
      if (response.status === 401 && tokens.get() && (await refreshTokens())) response = await send();
      if (!response.ok) throw await toApiError(response);
      return (await response.json()) as DataJob;
    },
    runImport: (jobId: number, layers: ImportPlanItem[]) =>
      request<DataJob>("POST", `/api/transfer/jobs/${jobId}/run/`, { layers }),
    startExport: (data: { project: number; layer_ids: number[]; format: ExportFormat; crs?: string | null; feature_ids?: number[] }) =>
      request<DataJob>("POST", "/api/transfer/jobs/exports/", data),
    getJob: (id: number) => request<DataJob>("GET", `/api/transfer/jobs/${id}/`),
    /** Brings OpenStreetMap features inside an area into the project, as layers (a background job). */
    openStreetMap: (data: { project: number; kinds: string[]; use_boundary?: boolean; area?: GeoJSONGeometry; area_crs?: string }) =>
      request<DataJob>("POST", "/api/transfer/jobs/openstreetmap/", data),
    listJobs: (projectId: number) => request<Page<DataJob>>("GET", `/api/transfer/jobs/${query({ project: projectId })}`),
    /** The finished export as a file (downloads are district data, so authenticated). */
    async downloadExport(job: Pick<DataJob, "id" | "result_name">): Promise<Blob> {
      const send = () => doFetch(`${root}/api/transfer/jobs/${job.id}/download/`, { headers: headers(false) });
      let response = await send();
      if (response.status === 401 && tokens.get() && (await refreshTokens())) response = await send();
      if (!response.ok) throw await toApiError(response);
      return response.blob();
    },

    // --- Readiness checklist ---------------------------------------------------------
    getChecklist: (projectId: number) => request<Checklist>("GET", `/api/projects/${projectId}/checklist/`),
    /** Adds items added to the template since the project started. */
    addMissingChecklistItems: (projectId: number) =>
      request<Checklist & { added: number }>("POST", `/api/projects/${projectId}/checklist/`),
    updateChecklistItem: (
      id: number,
      data: Partial<{ status: ChecklistStatus; owner: number | null; due_date: string | null; notes: string; linked_layer: number | null }>,
    ) => request<ChecklistItem>("PATCH", `/api/checklist-items/${id}/`, data),
    /** Creates a layer for a map-layer item (named after it, in its domain) and links it. */
    createChecklistLayer: (id: number) =>
      request<ChecklistItem & { layer: number }>("POST", `/api/checklist-items/${id}/create-layer/`),
    async uploadChecklistAttachment(itemId: number, file: File): Promise<ChecklistItem> {
      const form = new FormData();
      form.set("file", file);
      const send = () =>
        doFetch(`${root}/api/checklist-items/${itemId}/attachments/`, { method: "POST", headers: headers(false), body: form });
      let response = await send();
      if (response.status === 401 && tokens.get() && (await refreshTokens())) response = await send();
      if (!response.ok) throw await toApiError(response);
      return (await response.json()) as ChecklistItem;
    },
    deleteChecklistAttachment: (id: number) => request<void>("DELETE", `/api/checklist-attachments/${id}/`),
    downloadChecklistAttachment: (id: number) => blob(`/api/checklist-attachments/${id}/download/`),
    exportChecklist: (projectId: number, format: "csv" | "pdf") =>
      blob(`/api/projects/${projectId}/checklist/export/${query({ type: format })}`),
    readinessDashboard: () => request<ReadinessDashboard>("GET", "/api/readiness/"),
    getChecklistTemplate: () => request<ChecklistTemplate>("GET", "/api/readiness/template/"),
    customiseChecklistTemplate: () => request<ChecklistTemplate>("POST", "/api/readiness/template/"),
    revertChecklistTemplate: () => request<void>("DELETE", "/api/readiness/template/"),
    createTemplateItem: (data: Omit<TemplateItem, "id" | "order"> & { order?: number }) =>
      request<TemplateItem>("POST", "/api/readiness/template-items/", data),
    updateTemplateItem: (id: number, data: Partial<Omit<TemplateItem, "id">>) =>
      request<TemplateItem>("PATCH", `/api/readiness/template-items/${id}/`, data),
    deleteTemplateItem: (id: number) => request<void>("DELETE", `/api/readiness/template-items/${id}/`),

    // --- .spp project files -----------------------------------------------------------
    /** The whole project as a protected file, with the name the server gave it. */
    async saveProjectFile(projectId: number): Promise<{ blob: Blob; name: string }> {
      const send = () => doFetch(`${root}/api/projects/${projectId}/spp/`, { method: "POST", headers: headers(false) });
      let response = await send();
      if (response.status === 401 && tokens.get() && (await refreshTokens())) response = await send();
      if (!response.ok) throw await toApiError(response);
      const name = /filename="([^"]+)"/.exec(response.headers.get("content-disposition") ?? "")?.[1];
      return { blob: await response.blob(), name: name ?? `project-${projectId}.spp` };
    },
    /** Opens a .spp file as a new project in the current district. */
    async openProjectFile(file: File): Promise<SppReport> {
      const form = new FormData();
      form.set("file", file);
      const send = () => doFetch(`${root}/api/spp/open/`, { method: "POST", headers: headers(false), body: form });
      let response = await send();
      if (response.status === 401 && tokens.get() && (await refreshTokens())) response = await send();
      if (!response.ok) throw await toApiError(response);
      return (await response.json()) as SppReport;
    },
    /** Key ids and fingerprints (system administrators); never the keys. */
    sppKeys: () => request<SppKeys>("GET", "/api/spp/keys/"),

    // --- Field sync -------------------------------------------------------------------
    /** How a feature was recorded in the field (newest first); empty for office data. */
    featureCaptures: (featureId: number) => request<FieldCapture[]>("GET", `/api/sync/captures/${query({ feature: featureId })}`),
    featurePhotos: (featureId: number) => request<FieldPhoto[]>("GET", `/api/sync/photos/${query({ feature: featureId })}`),
    photoFile: (uuid: string) => blob(`/api/sync/photos/${uuid}/file/`),
    listConflicts: (projectId: number, status: "open" | "resolved" | "" = "open") =>
      request<SyncConflict[]>("GET", `/api/sync/conflicts/${query({ project: projectId, status })}`),
    getConflict: (id: number) => request<SyncConflictDetail>("GET", `/api/sync/conflicts/${id}/`),
    resolveConflict: (
      id: number,
      data: { resolution: ConflictResolution; properties?: Record<string, unknown>; use_field_geometry?: boolean },
    ) => request<SyncConflictDetail>("POST", `/api/sync/conflicts/${id}/resolve/`, data),
    /** Makes ground-truthing tasks for a checklist item's layer. */
    sendToField: (itemId: number) =>
      request<{ created: number; already_open: number; verified: number }>("POST", `/api/checklist-items/${itemId}/send-to-field/`),
    fieldTasks: (projectId: number) => request<FieldTaskSummary>("GET", `/api/sync/tasks/${query({ project: projectId })}`),

    // --- Drone and raster imagery ------------------------------------------------------
    listImagery: (projectId: number) => request<Imagery[]>("GET", `/api/imagery/${query({ project: projectId })}`),
    getImagery: (id: number) => request<Imagery>("GET", `/api/imagery/${id}/`),
    /**
     * Uploads a GeoTIFF in pieces, so a slow or unsteady connection can't lose
     * it: each piece is a short request, and after a dropped connection the
     * upload carries on from what the server has. Processing then runs in the
     * background (poll getImagery).
     */
    async uploadImagery(data: ImageryDetails & { file: File }, onProgress?: (fraction: number) => void): Promise<Imagery> {
      const { file, source, ...details } = data;
      const upload = await request<ImageryUpload>("POST", "/api/imagery/uploads/", { file_name: file.name, size: file.size });
      const base = `/api/imagery/uploads/${upload.id}`;
      let received = upload.received;
      let failures = 0;
      onProgress?.(0);
      while (received < file.size) {
        const piece = file.slice(received, received + upload.chunk_size);
        let response: Response;
        try {
          response = await sendBytes("POST", `${base}/chunk/${query({ offset: received })}`, piece);
        } catch (err) {
          // The connection dropped: wait, then the server says where to carry on.
          failures += 1;
          if (failures > UPLOAD_RETRIES) throw err;
          await new Promise((resolve) => setTimeout(resolve, retryDelay(failures)));
          continue;
        }
        if (!response.ok && response.status !== 409) throw await toApiError(response);
        // 409: the server's copy ends elsewhere (a retried piece); carry on from there.
        received = ((await response.json()) as ImageryUpload).received;
        failures = 0;
        onProgress?.(received / file.size);
      }
      const body: Record<string, unknown> = { ...details, captured_by: source };
      for (const key of Object.keys(body)) if (body[key] === undefined || body[key] === "") delete body[key];
      return request<Imagery>("POST", `${base}/finish/`, body);
    },
    updateImagery: (id: number, data: Partial<Pick<Imagery, "name" | "capture_date" | "source">>) =>
      request<Imagery>("PATCH", `/api/imagery/${id}/`, data),
    deleteImagery: (id: number) => request<void>("DELETE", `/api/imagery/${id}/`),
    makeContours: (id: number, interval: number) => request<ContourResult>("POST", `/api/imagery/${id}/contours/`, { interval }),
    /** A tile of the district's own imagery (null when the tile is empty). */
    async ownTile(path: string): Promise<Blob | null> {
      const send = () => doFetch(`${root}${path}`, { headers: headers(false) });
      let response = await send();
      if (response.status === 401 && tokens.get() && (await refreshTokens())) response = await send();
      if (response.status === 204) return null;
      if (!response.ok) throw await toApiError(response);
      return response.blob();
    },

    // --- Relationship layer -------------------------------------------------------------
    relationsRegistry: () => request<RelationsRegistry>("GET", "/api/relations/registry/"),
    getLayerRoles: (projectId: number) => request<{ roles: LayerRoleRow[] }>("GET", `/api/projects/${projectId}/layer-roles/`),
    setLayerRoles: (projectId: number, roles: { role: string; layer: number | null; config?: Record<string, unknown> }[]) =>
      request<{ roles: LayerRoleRow[] }>("PUT", `/api/projects/${projectId}/layer-roles/`, { roles }),
    latestRelationsRun: (projectId: number) =>
      request<{ latest: RelationsRun | null; summary: RelationsSummary | null }>("GET", `/api/projects/${projectId}/relations/run/`),
    runRelations: (projectId: number) => request<RelationsRun>("POST", `/api/projects/${projectId}/relations/run/`),
    listRelationships: (filters: { project?: number; feature?: number; type?: string; method?: string; status?: string; page?: number }) =>
      request<Page<RelationshipLink>>("GET", `/api/relationships/${query(filters)}`),
    confirmRelationship: (id: number, note = "") => request<RelationshipLink>("POST", `/api/relationships/${id}/confirm/`, { note }),
    rejectRelationship: (id: number, note = "") => request<RelationshipLink>("POST", `/api/relationships/${id}/reject/`, { note }),
    reopenRelationship: (id: number) => request<RelationshipLink>("POST", `/api/relationships/${id}/reopen/`),
    listStandards: () => request<DevelopmentStandard[]>("GET", "/api/standards/"),
    createStandard: (data: Partial<DevelopmentStandard>) => request<DevelopmentStandard>("POST", "/api/standards/", data),
    updateStandard: (id: number, data: Partial<DevelopmentStandard>) => request<DevelopmentStandard>("PATCH", `/api/standards/${id}/`, data),
    deleteStandard: (id: number) => request<void>("DELETE", `/api/standards/${id}/`),

    // --- Zoning (the national standards, the scheme register) ---------------------------
    nationalZones: () => request<NationalZones>("GET", "/api/relations/zones/"),
    /** Adopts LUSPA's standards for the district; `replace` also overwrites the district's own changes. */
    adoptNationalStandards: (data: { zones?: string[]; replace?: boolean } = {}) =>
      request<AdoptReport>("POST", "/api/standards/adopt-national/", data),
    /** Colours the project's zoning layer in the national colour codes. */
    colourZoningLayer: (projectId: number) =>
      request<{ layer: number; coloured: string[]; unknown: string[] }>("POST", `/api/projects/${projectId}/zoning-style/`),
    listZoningSchemes: (projectId: number) => request<ZoningScheme[]>("GET", `/api/zoning-schemes/${query({ project: projectId })}`),
    createZoningScheme: (data: Partial<ZoningScheme> & { project: number; name: string }) =>
      request<ZoningScheme>("POST", "/api/zoning-schemes/", data),
    updateZoningScheme: (id: number, data: Partial<ZoningScheme>) => request<ZoningScheme>("PATCH", `/api/zoning-schemes/${id}/`, data),
    deleteZoningScheme: (id: number) => request<void>("DELETE", `/api/zoning-schemes/${id}/`),

    // --- Permits ---------------------------------------------------------------------------
    permitRegistry: () => request<PermitRegistry>("GET", "/api/permits/registry/"),
    listPermits: (filters: { project?: number; status?: string; q?: string; overdue?: boolean } = {}) =>
      request<PermitList>("GET", `/api/permits/applications/${query({ ...filters, overdue: filters.overdue ? "true" : undefined })}`),
    getPermit: (id: number) => request<PermitApplication>("GET", `/api/permits/applications/${id}/`),
    /** Receives an application: it gets its number and its deadlines start. */
    createPermit: (data: NewPermit) => request<PermitApplication>("POST", "/api/permits/applications/", data),
    updatePermit: (id: number, data: Partial<Omit<NewPermit, "project" | "kind" | "received_on">>) =>
      request<PermitApplication>("PATCH", `/api/permits/applications/${id}/`, data),
    acknowledgePermit: (id: number, on?: string) => request<PermitApplication>("POST", `/api/permits/applications/${id}/acknowledge/`, { on }),
    checkPermit: (id: number) => request<PermitApplication>("POST", `/api/permits/applications/${id}/check/`),
    inspectPermit: (id: number, data: { on?: string; findings: Record<string, string>; summary?: string; purpose?: "application" | "completion" }) =>
      request<PermitApplication>("POST", `/api/permits/applications/${id}/inspect/`, data),
    commentOnPermit: (id: number, data: { agency: string; body: string; objection?: boolean }) =>
      request<PermitApplication>("POST", `/api/permits/applications/${id}/comments/`, data),
    reportPermit: (id: number, data: { recommendation: PermitDecision; report?: string; on?: string }) =>
      request<PermitApplication>("POST", `/api/permits/applications/${id}/report/`, data),
    decidePermit: (id: number, data: { decision: PermitDecision; reasons?: string; conditions?: string; on?: string }) =>
      request<PermitApplication>("POST", `/api/permits/applications/${id}/decide/`, data),
    recordPermitFee: (id: number, data: { stage: "processing" | "permit"; amount: string; receipt: string; paid_on?: string }) =>
      request<PermitApplication>("POST", `/api/permits/applications/${id}/fees/`, data),
    issuePermit: (id: number, on?: string) => request<PermitApplication>("POST", `/api/permits/applications/${id}/issue/`, { on }),
    certifyHabitation: (id: number, on?: string) => request<PermitApplication>("POST", `/api/permits/applications/${id}/habitation/`, { on }),
    withdrawPermit: (id: number, note = "") => request<PermitApplication>("POST", `/api/permits/applications/${id}/withdraw/`, { note }),
    async uploadPermitDocument(id: number, file: File, requirement = ""): Promise<PermitApplication> {
      const form = new FormData();
      form.set("file", file);
      if (requirement) form.set("requirement", requirement);
      const send = () => doFetch(`${root}/api/permits/applications/${id}/documents/`, { method: "POST", headers: headers(false), body: form });
      let response = await send();
      if (response.status === 401 && tokens.get() && (await refreshTokens())) response = await send();
      if (!response.ok) throw await toApiError(response);
      return (await response.json()) as PermitApplication;
    },
    downloadPermitDocument: (id: number) => blob(`/api/permits/documents/${id}/download/`),
    deletePermitDocument: (id: number) => request<void>("DELETE", `/api/permits/documents/${id}/`),
    /** The acknowledgement of receipt, the refusal or deferral letter, or the certificate, as PDF. */
    permitPaper: (id: number, paper: "acknowledgement" | "letter" | "certificate" | "habitation-certificate" | "land-use-certificate") => blob(`/api/permits/applications/${id}/${paper}/`),
    listPermitFees: () => request<PermitFee[]>("GET", "/api/permits/fees/"),
    createPermitFee: (data: Omit<PermitFee, "id" | "updated_at">) => request<PermitFee>("POST", "/api/permits/fees/", data),
    updatePermitFee: (id: number, data: Partial<PermitFee>) => request<PermitFee>("PATCH", `/api/permits/fees/${id}/`, data),
    deletePermitFee: (id: number) => request<void>("DELETE", `/api/permits/fees/${id}/`),
    /** The project as a plan sheet (PDF) at a true scale in its own grid. `scale` is the scale used. */
    async planSheet(projectId: number, options: { paper?: string; scale?: number; title?: string } = {}): Promise<{ blob: Blob; scale: number }> {
      const send = () => doFetch(`${root}/api/projects/${projectId}/sheet/${query(options)}`, { headers: headers(false) });
      let response = await send();
      if (response.status === 401 && tokens.get() && (await refreshTokens())) response = await send();
      if (!response.ok) throw await toApiError(response);
      return { blob: await response.blob(), scale: Number(response.headers.get("X-Sheet-Scale") ?? 0) };
    },

    // --- Re-zoning, change of use, subdivision and consolidation ---------------------------
    landRegistry: () => request<LandRegistry>("GET", "/api/land/registry/"),
    listLandApplications: (filters: { project?: number; status?: string; kind?: string } = {}) =>
      request<{ results: LandSummary[]; summary: { total: number; open: number; overdue: number } }>("GET", `/api/land/applications/${query(filters)}`),
    getLandApplication: (id: number) => request<LandApplication>("GET", `/api/land/applications/${id}/`),
    receiveLandApplication: (data: NewLandApplication) => request<LandApplication>("POST", "/api/land/applications/", data),
    landStep: (id: number, data: { step: string; on?: string; note?: string }) => request<LandApplication>("POST", `/api/land/applications/${id}/step/`, data),
    landComment: (id: number, data: { kind: string; name: string; contact?: string; text: string; on?: string }) =>
      request<LandApplication>("POST", `/api/land/applications/${id}/comments/`, data),
    landRespond: (id: number, data: { comment: number; response: string; on?: string }) => request<LandApplication>("POST", `/api/land/applications/${id}/respond/`, data),
    landAssess: (id: number, answers: Record<string, { met: boolean; note?: string }>) => request<LandApplication>("POST", `/api/land/applications/${id}/assess/`, { answers }),
    landDefer: (id: number, reason: string) => request<LandApplication>("POST", `/api/land/applications/${id}/defer/`, { reason }),
    landDecide: (id: number, data: { approve: boolean; conditions?: string; reasons?: string; on?: string }) =>
      request<LandApplication>("POST", `/api/land/applications/${id}/decide/`, data),
    landWithdraw: (id: number) => request<LandApplication>("POST", `/api/land/applications/${id}/withdraw/`),
    /** Writes an approved re-zoning to the map: the new zone on each parcel. */
    landApply: (id: number) =>
      request<{ written: { parcels_changed: number; field: string; zoning_layer: boolean }; application: LandApplication }>("POST", `/api/land/applications/${id}/apply/`),
    landPaper: (id: number, kind: string) => blob(`/api/land/applications/${id}/paper/${query({ kind })}`),
    publicLandApplications: (code: string) => open<{ results: PublicLandApplication[] }>(`/api/public/rooms/${encodeURIComponent(code)}/land-applications/`),

    // --- Making a local plan, and its consultation -----------------------------------------
    getPlanProcess: (projectId: number) => request<PlanProcess>("GET", `/api/projects/${projectId}/plan/`),
    updatePlanProcess: (projectId: number, data: PlanSettings) => request<PlanProcess>("PATCH", `/api/projects/${projectId}/plan/`, data),
    planStep: (projectId: number, data: { step: string; on?: string; note?: string }) => request<PlanProcess>("POST", `/api/projects/${projectId}/plan/step/`, data),
    planContent: (projectId: number, items: Record<string, { covered: boolean; note?: string }>) => request<PlanProcess>("POST", `/api/projects/${projectId}/plan/content/`, { items }),
    planPaper: (projectId: number, kind: string) => blob(`/api/projects/${projectId}/plan/paper/${query({ kind })}`),
    recordConsultation: (projectId: number, data: NewConsultation) => request<PlanProcess>("POST", `/api/projects/${projectId}/plan/consultations/`, data),
    displayConsultation: (consultationId: number) => request<PlanProcess>("POST", `/api/plan-consultations/${consultationId}/display/`),
    consultationMinutes: (consultationId: number) => blob(`/api/plan-consultations/${consultationId}/minutes/`),
    recordPlanComment: (projectId: number, data: { name: string; contact?: string; topic?: string; text: string; on?: string }) =>
      request<PlanProcess>("POST", `/api/projects/${projectId}/plan/comments/`, data),
    replyPlanComment: (commentId: number, response: string) => request<PlanProcess>("POST", `/api/plan-comments/${commentId}/reply/`, { response }),
    publicPlans: (code: string) => open<{ results: PublicPlan[]; topics: { code: string; label: string }[] }>(`/api/public/rooms/${encodeURIComponent(code)}/plans/`),
    /** A comment on a draft local plan, from anyone, while its sixty days run. */
    async sendPlanComment(code: string, projectId: number, data: { name: string; contact?: string; topic?: string; text: string }) {
      const response = await doFetch(`${root}/api/public/rooms/${encodeURIComponent(code)}/plans/${projectId}/comments/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      if (!response.ok) throw await toApiError(response);
      return (await response.json()) as { received_on: string; comments_close_on: string | null };
    },

    // --- Property register, rates and betterment ------------------------------------------
    registerSummary: (projectId: number) => request<RegisterSummary>("GET", `/api/projects/${projectId}/register/`),
    listRegister: (projectId: number, filters: { status?: string; q?: string } = {}) =>
      request<{ results: RegisterProperty[]; count: number }>("GET", `/api/revenue/properties/${query({ project: projectId, ...filters })}`),
    updateProperty: (id: number, data: Partial<Pick<RegisterProperty, "address" | "use" | "owner_name" | "owner_contact" | "valuation_ref" | "rateable_value" | "valued_on" | "revenue_ref">>) =>
      request<RegisterProperty>("PATCH", `/api/revenue/properties/${id}/`, data),
    recordRatePayment: (id: number, data: { year: number; amount: string; on?: string }) =>
      request<RegisterProperty>("POST", `/api/revenue/properties/${id}/payment/`, data),
    buildRegister: (projectId: number) => request<{ added: number; already: number; total: number }>("POST", `/api/projects/${projectId}/register/build/`, {}),
    billYear: (projectId: number, year: number) =>
      request<{ billed: number; total: string; skipped: { number: string; reason: string }[]; skipped_count: number }>("POST", `/api/projects/${projectId}/register/bills/`, { year }),
    mapRegister: (projectId: number) => request<{ layer: number; written: number; removed: number }>("POST", `/api/projects/${projectId}/register/map/`, {}),
    async importRegister(projectId: number, what: "valuations" | "revenue", file: File): Promise<RegisterImport> {
      const form = new FormData();
      form.set("file", file);
      const send = () => doFetch(`${root}/api/projects/${projectId}/register/${what}/`, { method: "POST", headers: headers(false), body: form });
      let response = await send();
      if (response.status === 401 && tokens.get() && (await refreshTokens())) response = await send();
      if (!response.ok) throw await toApiError(response);
      return (await response.json()) as RegisterImport;
    },
    registerCsv: (projectId: number) => blob(`/api/projects/${projectId}/register/csv/`),
    listRateBands: () => request<RateBand[]>("GET", "/api/revenue/rates/"),
    createRateBand: (data: { year: number; use: PropertyUse; impost: string; minimum?: string; flat?: string | null }) =>
      request<RateBand>("POST", "/api/revenue/rates/", data),
    deleteRateBand: (id: number) => request<void>("DELETE", `/api/revenue/rates/${id}/`),
    listBetterment: (projectId: number) => request<{ results: BettermentScheme[] }>("GET", `/api/revenue/betterment/${query({ project: projectId })}`),
    getBetterment: (id: number) => request<BettermentScheme>("GET", `/api/revenue/betterment/${id}/`),
    createBetterment: (data: { project: number; name: string; works?: string; works_feature?: number | null; reach_m?: string; completed_on: string; basis: "sum" | "rate"; amount: string }) =>
      request<BettermentScheme>("POST", "/api/revenue/betterment/", data),
    updateBetterment: (id: number, data: Partial<{ name: string; reach_m: string; basis: "sum" | "rate"; amount: string; works_feature: number | null }>) =>
      request<BettermentScheme>("PATCH", `/api/revenue/betterment/${id}/`, data),
    findBettered: (id: number) => request<BettermentScheme>("POST", `/api/revenue/betterment/${id}/find/`, {}),
    publishBetterment: (id: number, how: string, on?: string) => request<BettermentScheme>("POST", `/api/revenue/betterment/${id}/publish/`, { how, on }),
    bettermentNotice: (id: number) => blob(`/api/revenue/betterment/${id}/notice/`),
    updateCharge: (id: number, data: Partial<{ increase: string | null; served_on: string | null; paid: string; paid_on: string | null }>) =>
      request<BettermentCharge>("PATCH", `/api/revenue/betterment-charges/${id}/`, data),
    chargePaper: (id: number, kind: "assessment" | "certificate") => blob(`/api/revenue/betterment-charges/${id}/paper/${query({ kind })}`),

    // --- Returns and national data exchange ------------------------------------------------
    districtReturn: (period: string) => request<DistrictReturn>("GET", `/api/reports/returns/${query({ period })}`),
    districtReturnFile: (period: string, type: "csv" | "pdf") => blob(`/api/reports/returns/${query({ period, type })}`),
    listExchangeKeys: () => request<{ keys: ExchangeKey[]; scopes: Record<string, string> }>("GET", "/api/exchange/keys/"),
    createExchangeKey: (data: { name: string; scopes: string[] }) => request<ExchangeKey>("POST", "/api/exchange/keys/", data),
    revokeExchangeKey: (id: number) => request<ExchangeKey>("POST", `/api/exchange/keys/${id}/revoke/`, {}),

    // --- Street addressing -----------------------------------------------------------------
    /** Proposes street codes and property numbers; changes nothing. */
    proposeAddresses: (projectId: number, options: AddressingOptions = {}) =>
      request<AddressProposal>("GET", `/api/projects/${projectId}/addressing/${query(options)}`),
    addressSchedule: (projectId: number, options: AddressingOptions = {}) => blob(`/api/projects/${projectId}/addressing/${query({ ...options, type: "csv" })}`),
    /** Writes the proposal to the map. */
    applyAddresses: (projectId: number, options: AddressingOptions = {}) =>
      request<{ written: { streets: number; properties: number }; numbered: number }>("POST", `/api/projects/${projectId}/addressing/`, options),

    // --- The district's statutory deadlines -------------------------------------------------
    compliance: () => request<Compliance>("GET", "/api/reports/compliance/"),
    compliancePdf: () => blob("/api/reports/compliance/pdf/"),

    // --- Enforcement ------------------------------------------------------------------------
    enforcementRegistry: () => request<EnforcementRegistry>("GET", "/api/enforcement/registry/"),
    listCases: (filters: { project?: number; status?: string } = {}) => request<CaseList>("GET", `/api/enforcement/cases/${query(filters)}`),
    getCase: (id: number) => request<EnforcementCase>("GET", `/api/enforcement/cases/${id}/`),
    openCase: (data: NewCase) => request<EnforcementCase>("POST", "/api/enforcement/cases/", data),
    updateCase: (id: number, data: Partial<Omit<NewCase, "project" | "opened_on" | "origin">>) =>
      request<EnforcementCase>("PATCH", `/api/enforcement/cases/${id}/`, data),
    issueNotice: (caseId: number, data: { kind: string; grounds: string; remedy?: string; comply_by?: string | null; on?: string }) =>
      request<EnforcementCase>("POST", `/api/enforcement/cases/${caseId}/notices/`, data),
    serveNotice: (noticeId: number, data: { method: string; on?: string; note?: string }) =>
      request<EnforcementCase>("POST", `/api/enforcement/notices/${noticeId}/serve/`, data),
    noticeComplied: (noticeId: number) => request<EnforcementCase>("POST", `/api/enforcement/notices/${noticeId}/complied/`),
    noticePaper: (noticeId: number) => blob(`/api/enforcement/notices/${noticeId}/paper/`),
    closeCase: (id: number, data: { status: "rectified" | "enforced" | "dropped"; outcome?: string; cost?: string | null; cost_recovered?: string | null; on?: string }) =>
      request<EnforcementCase>("POST", `/api/enforcement/cases/${id}/close/`, data),
    listDetections: (projectId: number) => request<{ results: DetectionRun[] }>("GET", `/api/projects/${projectId}/detections/`),
    /** Compares two orthophotos for changes on the ground. Can take a minute. */
    detectChanges: (projectId: number, before: number, after: number) =>
      request<DetectionRun>("POST", `/api/projects/${projectId}/detections/`, { before, after }),

    // --- The Public Data Room: staff ---------------------------------------------------------
    getDataRoom: () => request<DataRoomSettings>("GET", "/api/dataroom/"),
    updateDataRoom: (data: Partial<Omit<DataRoomSettings, "code" | "updated_at">>) => request<DataRoomSettings>("PATCH", "/api/dataroom/", data),
    listPublications: () => request<Publication[]>("GET", "/api/dataroom/publications/"),
    publishProject: (project: number) => request<Publication>("POST", "/api/dataroom/publications/", { project }),
    updatePublication: (id: number, data: Partial<Pick<Publication, "permits" | "zoning">>) =>
      request<Publication>("PATCH", `/api/dataroom/publications/${id}/`, data),
    unpublishProject: (id: number) => request<void>("DELETE", `/api/dataroom/publications/${id}/`),
    listRoomDocuments: () => request<RoomDocument[]>("GET", "/api/dataroom/documents/"),
    async uploadRoomDocument(data: { file: File; kind: RoomDocumentKind; title: string; description?: string; display_from?: string; display_until?: string }): Promise<RoomDocument> {
      const form = new FormData();
      for (const [key, value] of Object.entries(data)) {
        if (value !== undefined && value !== "") form.set(key, value instanceof File ? value : String(value));
      }
      const send = () => doFetch(`${root}/api/dataroom/documents/`, { method: "POST", headers: headers(false), body: form });
      let response = await send();
      if (response.status === 401 && tokens.get() && (await refreshTokens())) response = await send();
      if (!response.ok) throw await toApiError(response);
      return (await response.json()) as RoomDocument;
    },
    deleteRoomDocument: (id: number) => request<void>("DELETE", `/api/dataroom/documents/${id}/`),
    listInformationRequests: () => request<InformationRequests>("GET", "/api/dataroom/requests/"),
    answerInformationRequest: (id: number, answer: string, declined = false) =>
      request<InformationRequest>("POST", `/api/dataroom/requests/${id}/answer/`, { answer, declined }),

    // --- The Public Data Room: anyone, no sign-in -----------------------------------------
    publicRooms: () => open<{ code: string; assembly: string }[]>("/api/public/rooms/"),
    /** Null when that Assembly's room isn't open online. */
    publicRoom: (code: string) => open<PublicRoom>(`/api/public/rooms/${encodeURIComponent(code)}/`, true),
    publicRegister: (code: string, filters: { q?: string; status?: string } = {}) =>
      open<{ results: RegisterEntry[] }>(`/api/public/rooms/${encodeURIComponent(code)}/register/${query(filters)}`),
    publicNotices: (code: string) => open<{ results: PublicNotice[] }>(`/api/public/rooms/${encodeURIComponent(code)}/notices/`),
    publicStatus: (code: string, number: string) => open<PublicStatus>(`/api/public/rooms/${encodeURIComponent(code)}/status/${query({ number })}`, true),
    publicZone: (code: string, lon: number, lat: number) => open<PublicZone>(`/api/public/rooms/${encodeURIComponent(code)}/zone/${query({ lon, lat })}`),
    publicDocumentUrl: (code: string, id: number) => `${root}/api/public/rooms/${encodeURIComponent(code)}/documents/${id}/`,
    async askDataRoom(code: string, data: { name: string; phone?: string; email?: string; subject: string; body: string }) {
      const response = await doFetch(`${root}/api/public/rooms/${encodeURIComponent(code)}/requests/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      if (!response.ok) throw await toApiError(response);
      return (await response.json()) as { reference: string; received_on: string; answer_due_on: string };
    },

    /** Checks a certificate's code against the Assembly's record. Needs no sign-in. */
    async verifyPermit(token: string): Promise<PermitVerification | null> {
      const response = await doFetch(`${root}/api/public/permits/${encodeURIComponent(token)}/`);
      if (response.status === 404) return null;
      if (!response.ok) throw await toApiError(response);
      return (await response.json()) as PermitVerification;
    },

    // --- Audit log ---------------------------------------------------------------
    listAudit: (filters: AuditFilters = {}) =>
      request<Page<AuditEntry>>("GET", `/api/audit/${query(filters)}`),
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;
