// Calls to the platform's server. Mirrors the web app's client: bearer token,
// X-District-ID, and one refresh attempt on a 401.

import type { FieldPackage, Me, ServerLayer, ServerProject, Tokens } from "../types";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

/** The server couldn't be reached at all (no network, wrong address). */
export class OfflineError extends Error {
  constructor() {
    super("Can't reach the server. Check the connection and the server address.");
  }
}

export function normaliseServer(input: string): string {
  let url = input.trim().replace(/\/+$/, "");
  if (url && !/^https?:\/\//i.test(url)) url = `https://${url}`;
  return url.replace(/\/api$/i, "");
}

function messageFrom(body: unknown, status: number): string {
  if (body && typeof body === "object") {
    const values = Array.isArray(body) ? body : Object.values(body as Record<string, unknown>);
    const flat = values.flat(3).filter((v): v is string => typeof v === "string");
    if (flat.length) return flat.join(" ");
  }
  return `The server answered HTTP ${status}.`;
}

export interface Session {
  server: string;
  tokens: Tokens | null;
  districtId: number | null;
  onTokens(tokens: Tokens | null): void;
}

export function createApi(session: Session) {
  async function send(path: string, init: RequestInit, auth: boolean): Promise<Response> {
    const headers = new Headers(init.headers);
    if (auth && session.tokens) headers.set("Authorization", `Bearer ${session.tokens.access}`);
    if (auth && session.districtId) headers.set("X-District-ID", String(session.districtId));
    try {
      return await fetch(`${session.server}${path}`, { ...init, headers });
    } catch {
      throw new OfflineError();
    }
  }

  async function refresh(): Promise<boolean> {
    if (!session.tokens?.refresh) return false;
    const response = await send(
      "/api/auth/refresh/",
      { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh: session.tokens.refresh }) },
      false,
    );
    if (!response.ok) return false;
    const next = (await response.json()) as Partial<Tokens>;
    session.tokens = { access: next.access!, refresh: next.refresh ?? session.tokens.refresh };
    session.onTokens(session.tokens);
    return true;
  }

  async function request<T>(method: string, path: string, body?: unknown, auth = true): Promise<T> {
    const init: RequestInit = {
      method,
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    };
    let response = await send(path, init, auth);
    if (response.status === 401 && auth && (await refresh())) response = await send(path, init, auth);
    if (!response.ok) {
      let parsed: unknown = null;
      try {
        parsed = await response.json();
      } catch {
        // not JSON
      }
      throw new ApiError(messageFrom(parsed, response.status), response.status);
    }
    return (await response.json()) as T;
  }

  return {
    async login(email: string, password: string): Promise<Tokens> {
      const tokens = await request<Tokens>("POST", "/api/auth/login/", { email, password }, false);
      session.tokens = { access: tokens.access, refresh: tokens.refresh };
      session.onTokens(session.tokens);
      return session.tokens;
    },
    me: () => request<Me>("GET", "/api/auth/me/"),
    async projects(): Promise<ServerProject[]> {
      const page = await request<{ results: ServerProject[] }>("GET", "/api/projects/");
      return page.results;
    },
    layers: (projectId: number) => request<ServerLayer[]>("GET", `/api/layers/?project=${projectId}`),
    fieldPackage: (projectId: number, layerIds: number[]) =>
      request<FieldPackage>("GET", `/api/projects/${projectId}/field-package/?layers=${layerIds.join(",")}`),
    /** Where to download an offline basemap from, with the headers it needs (a fresh token). */
    async basemapRequest(projectId: number, sourceId: number, maxZoom?: number): Promise<{ url: string; headers: Record<string, string> }> {
      await refresh(); // downloads can't retry on a 401, so start with a fresh token
      const zoom = maxZoom === undefined ? "" : `&max_zoom=${maxZoom}`;
      return {
        url: `${session.server}/api/projects/${projectId}/field-package/basemap/?source=${sourceId}${zoom}`,
        headers: {
          Authorization: `Bearer ${session.tokens?.access ?? ""}`,
          "X-District-ID": String(session.districtId ?? ""),
        },
      };
    },
  };
}

export type Api = ReturnType<typeof createApi>;
