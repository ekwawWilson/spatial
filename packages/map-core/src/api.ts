// Typed client for the backend API, shared by the web and mobile apps.

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

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function createApiClient(baseUrl = "", fetchImpl: typeof fetch = fetch) {
  const root = baseUrl.replace(/\/$/, "");

  return {
    // A failing service returns 503 with the same body, which callers still
    // want to show, so only non-JSON responses are treated as errors.
    async getHealth(): Promise<HealthReport> {
      const response = await fetchImpl(`${root}/api/health/`);
      const type = response.headers.get("content-type") ?? "";
      if (!type.includes("application/json")) {
        throw new ApiError(`Health check failed (HTTP ${response.status})`, response.status);
      }
      return (await response.json()) as HealthReport;
    },
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;
