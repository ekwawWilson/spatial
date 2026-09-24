import type { Me } from "@spatial/map-core";
import { vi } from "vitest";

type Handler = (body: unknown, headers: Headers) => { status?: number; body?: unknown };

/** A tiny in-memory backend: routes "METHOD /path" (query string ignored) to
 * handlers, and records every call so tests can assert on headers and bodies. */
export function fakeBackend(routes: Record<string, Handler>) {
  const calls: { method: string; path: string; body: unknown; headers: Headers }[] = [];
  const fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://test");
    const method = init?.method ?? "GET";
    const headers = new Headers(init?.headers);
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ method, path: url.pathname + url.search, body, headers });
    const handler = routes[`${method} ${url.pathname}`];
    if (!handler) return new Response(JSON.stringify({ detail: "Not found." }), { status: 404 });
    const { status = 200, body: out } = handler(body, headers);
    if (status === 204) return new Response(null, { status });
    return new Response(JSON.stringify(out ?? {}), { status, headers: { "content-type": "application/json" } });
  });
  return { fetch: fetch as unknown as typeof globalThis.fetch, calls };
}

export function makeMe(overrides: Partial<Me> = {}): Me {
  return {
    id: 1,
    email: "ama@example.test",
    first_name: "Ama",
    last_name: "Mensah",
    is_system_admin: false,
    memberships: [
      {
        district: { id: 10, name: "Sample Municipal Assembly", code: "SMA" },
        role: "district_admin",
        permissions: [
          "audit.view",
          "crs.manage",
          "district.view",
          "feature.edit",
          "layer.edit",
          "membership.manage",
          "membership.view",
          "project.edit",
          "project.view",
        ],
      },
      {
        district: { id: 20, name: "Other District Assembly", code: "ODA" },
        role: "viewer",
        permissions: ["district.view", "project.view"],
      },
    ],
    ...overrides,
  };
}

export const emptyPage = { count: 0, next: null, previous: null, results: [] };
