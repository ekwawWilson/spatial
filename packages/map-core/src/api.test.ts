import { describe, expect, it, vi } from "vitest";

import { ApiError, createApiClient, type HealthReport } from "./api";
import { memoryTokenStore } from "./tokens";

const healthy: HealthReport = {
  ok: true,
  database: { ok: true, postgis: "3.5.2", proj: "9.4.1" },
  gdal: { ok: true, version: "3.10.3", missing_drivers: [] },
  redis: { ok: true },
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function header(call: unknown[], name: string): string | null {
  const init = call[1] as RequestInit | undefined;
  return new Headers(init?.headers).get(name);
}

describe("getHealth", () => {
  it("calls the health endpoint under the base URL", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(json(healthy));
    const report = await createApiClient({ baseUrl: "http://api.test/", fetch: fetchImpl }).getHealth();
    expect(fetchImpl.mock.calls[0]?.[0]).toBe("http://api.test/api/health/");
    expect(report.ok).toBe(true);
  });

  it("returns the report when a service is down (HTTP 503)", async () => {
    const down = { ...healthy, ok: false, redis: { ok: false, error: "refused" } };
    const fetchImpl = vi.fn().mockResolvedValue(json(down, 503));
    const report = await createApiClient({ fetch: fetchImpl }).getHealth();
    expect(report.redis.error).toBe("refused");
  });

  it("throws ApiError on a non-JSON response", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response("Bad gateway", { status: 502 }));
    await expect(createApiClient({ fetch: fetchImpl }).getHealth()).rejects.toBeInstanceOf(ApiError);
  });
});

describe("authenticated requests", () => {
  it("sends the access token and the active district", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(json({ count: 0, results: [] }));
    const api = createApiClient({
      fetch: fetchImpl,
      tokens: memoryTokenStore({ access: "A1", refresh: "R1" }),
      getDistrictId: () => 7,
    });
    await api.listMembers();
    const call = fetchImpl.mock.calls[0] as unknown[];
    expect(header(call, "Authorization")).toBe("Bearer A1");
    expect(header(call, "X-District-ID")).toBe("7");
  });

  it("login stores the tokens and returns the user", async () => {
    const tokens = memoryTokenStore();
    const fetchImpl = vi.fn().mockResolvedValue(json({ access: "A", refresh: "R", user: { email: "k@x.test" } }));
    const me = await createApiClient({ fetch: fetchImpl, tokens }).login("k@x.test", "pw");
    expect(me.email).toBe("k@x.test");
    expect(tokens.get()).toEqual({ access: "A", refresh: "R" });
  });

  it("refreshes an expired access token once and retries", async () => {
    const tokens = memoryTokenStore({ access: "old", refresh: "R1" });
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce(json({ detail: "expired" }, 401))
      .mockResolvedValueOnce(json({ access: "new", refresh: "R2" }))
      .mockResolvedValueOnce(json({ id: 1, email: "k@x.test" }));
    const me = await createApiClient({ fetch: fetchImpl, tokens }).me();
    expect(me.email).toBe("k@x.test");
    expect(fetchImpl.mock.calls[1]?.[0]).toBe("/api/auth/refresh/");
    expect(header(fetchImpl.mock.calls[2] as unknown[], "Authorization")).toBe("Bearer new");
    expect(tokens.get()).toEqual({ access: "new", refresh: "R2" });
  });

  it("shares one refresh between concurrent requests", async () => {
    const tokens = memoryTokenStore({ access: "old", refresh: "R1" });
    let refreshCalls = 0;
    const fetchImpl = vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/auth/refresh/") {
        refreshCalls += 1;
        return json({ access: "new", refresh: "R2" });
      }
      const auth = new Headers(init?.headers).get("Authorization");
      return auth === "Bearer new" ? json({ ok: true }) : json({ detail: "expired" }, 401);
    });
    const api = createApiClient({ fetch: fetchImpl as unknown as typeof fetch, tokens });
    await Promise.all([api.me(), api.listDistricts(), api.listRegions()]);
    expect(refreshCalls).toBe(1);
  });

  it("ends the session when the refresh token is rejected", async () => {
    const tokens = memoryTokenStore({ access: "old", refresh: "R1" });
    const onSessionExpired = vi.fn();
    const fetchImpl = vi
      .fn()
      .mockResolvedValueOnce(json({ detail: "expired" }, 401))
      .mockResolvedValueOnce(json({ detail: "blacklisted" }, 401));
    const api = createApiClient({ fetch: fetchImpl, tokens, onSessionExpired });
    await expect(api.me()).rejects.toMatchObject({ status: 401 });
    expect(tokens.get()).toBeNull();
    expect(onSessionExpired).toHaveBeenCalledOnce();
  });

  it("exposes field errors from a 400 response", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(json({ email: ["This person is already a member."] }, 400));
    const api = createApiClient({ fetch: fetchImpl, tokens: memoryTokenStore({ access: "A", refresh: "R" }) });
    const error = await api.addMember({ email: "a@x.test", role: "viewer" }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).fields.email).toEqual(["This person is already a member."]);
    expect((error as ApiError).message).toBe("This person is already a member.");
  });

  it("builds audit filter query strings, skipping empty values", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(json({ count: 0, results: [] }));
    await createApiClient({ fetch: fetchImpl }).listAudit({ table: "core_membership", action: undefined, page: 2 });
    expect(fetchImpl.mock.calls[0]?.[0]).toBe("/api/audit/?table=core_membership&page=2");
  });

  it("logout clears tokens even if the server call fails", async () => {
    const tokens = memoryTokenStore({ access: "A", refresh: "R" });
    const fetchImpl = vi.fn().mockRejectedValue(new Error("offline"));
    await createApiClient({ fetch: fetchImpl, tokens }).logout();
    expect(tokens.get()).toBeNull();
  });
});
