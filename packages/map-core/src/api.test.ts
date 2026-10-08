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

describe("uploadImagery", () => {
  /** A fake server that keeps the bytes it has; `drop` makes listed PUTs fail like a dropped connection. */
  function server(chunkSize: number, drop: number[] = []) {
    let stored = new Uint8Array(0);
    let puts = 0;
    const offsets: number[] = [];
    const fetchImpl = vi.fn(async (url: string, init?: RequestInit) => {
      const path = url.replace(/\?.*$/, "");
      if (path === "/api/imagery/uploads/") return json({ id: "u1", file_name: "f.tif", size: 10, received: 0, chunk_size: chunkSize }, 201);
      if (path.endsWith("/chunk/")) {
        puts += 1;
        const offset = Number(new URL(url, "http://x").searchParams.get("offset"));
        offsets.push(offset);
        const body = new Uint8Array(await (init?.body as Blob).arrayBuffer());
        if (drop.includes(puts)) {
          // The bytes arrived but the answer was lost.
          if (offset === stored.length) stored = new Uint8Array([...stored, ...body]);
          throw new TypeError("Failed to fetch");
        }
        if (offset !== stored.length) return json({ id: "u1", received: stored.length }, 409);
        stored = new Uint8Array([...stored, ...body]);
        return json({ id: "u1", received: stored.length });
      }
      if (path.endsWith("/finish/")) return json({ id: 5, ...JSON.parse(String(init?.body)) }, 201);
      throw new Error(`unexpected ${url}`);
    });
    return { fetchImpl, offsets, stored: () => stored };
  }

  const file = () => new File([new Uint8Array([0, 1, 2, 3, 4, 5, 6, 7, 8, 9])], "f.tif");

  it("sends the file in pieces, reports progress, then finishes with the details", async () => {
    const fake = server(4);
    const progress: number[] = [];
    const api = createApiClient({ fetch: fake.fetchImpl as typeof fetch, retryDelay: () => 0 });
    const result = await api.uploadImagery({ project: 3, kind: "ortho", file: file(), name: "", source: "Drone team" }, (p) => progress.push(p));
    expect(fake.offsets).toEqual([0, 4, 8]);
    expect(Array.from(fake.stored())).toEqual([0, 1, 2, 3, 4, 5, 6, 7, 8, 9]);
    expect(progress).toEqual([0, 0.4, 0.8, 1]);
    // Empty values are left out; "source" is sent as captured_by.
    expect(result).toEqual({ id: 5, project: 3, kind: "ortho", captured_by: "Drone team" });
    const put = fake.fetchImpl.mock.calls[1] as unknown[];
    expect(header(put, "Content-Type")).toBe("application/octet-stream");
  });

  it("carries on after a dropped connection without sending bytes twice", async () => {
    const fake = server(4, [2]);
    const api = createApiClient({ fetch: fake.fetchImpl as typeof fetch, retryDelay: () => 0 });
    await api.uploadImagery({ project: 3, kind: "ortho", file: file() });
    // Piece 2 arrived but its answer was lost; the retry is refused (409) and the
    // upload carries on from where the server's copy ends.
    expect(fake.offsets).toEqual([0, 4, 4, 8]);
    expect(Array.from(fake.stored())).toEqual([0, 1, 2, 3, 4, 5, 6, 7, 8, 9]);
  });

  it("gives up after repeated failures", async () => {
    const fake = server(4, [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]);
    const api = createApiClient({ fetch: fake.fetchImpl as typeof fetch, retryDelay: () => 0 });
    await expect(api.uploadImagery({ project: 3, kind: "ortho", file: file() })).rejects.toThrow("Failed to fetch");
  });
});
