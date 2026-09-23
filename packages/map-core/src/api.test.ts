import { describe, expect, it, vi } from "vitest";

import { ApiError, createApiClient, type HealthReport } from "./api";

const healthy: HealthReport = {
  ok: true,
  database: { ok: true, postgis: "3.5.2", proj: "9.4.1" },
  gdal: { ok: true, version: "3.10.3", missing_drivers: [] },
  redis: { ok: true },
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("createApiClient.getHealth", () => {
  it("calls the health endpoint under the base URL", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse(healthy));
    const report = await createApiClient("http://api.test/", fetchImpl).getHealth();
    expect(fetchImpl).toHaveBeenCalledWith("http://api.test/api/health/");
    expect(report.ok).toBe(true);
  });

  it("returns the report when a service is down (HTTP 503)", async () => {
    const down = { ...healthy, ok: false, redis: { ok: false, error: "refused" } };
    const fetchImpl = vi.fn().mockResolvedValue(jsonResponse(down, 503));
    const report = await createApiClient("", fetchImpl).getHealth();
    expect(report.redis.error).toBe("refused");
  });

  it("throws ApiError on a non-JSON response", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(new Response("Bad gateway", { status: 502 }));
    await expect(createApiClient("", fetchImpl).getHealth()).rejects.toBeInstanceOf(ApiError);
  });
});
