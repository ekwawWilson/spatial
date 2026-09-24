// Typed client for the backend API, shared by the web and mobile apps.

import { memoryTokenStore, type TokenStore } from "./tokens";
import type {
  AuditEntry,
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
}

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
    createFeature: (layerId: number, data: { geometry?: GeoJSONGeometry | null; properties?: Record<string, unknown> }) =>
      request<MapFeature>("POST", `/api/layers/${layerId}/features/`, data),
    /** 409 means someone else saved first; the error carries the current feature. */
    updateFeature: (
      id: number,
      data: { version: number; geometry?: GeoJSONGeometry | null; properties?: Record<string, unknown> },
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

    // --- Audit log ---------------------------------------------------------------
    listAudit: (filters: AuditFilters = {}) =>
      request<Page<AuditEntry>>("GET", `/api/audit/${query(filters)}`),
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;
