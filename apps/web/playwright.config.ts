import { defineConfig } from "@playwright/test";

// Runs against the full docker-compose stack (`make up`), not a mocked API.
export default defineConfig({
  testDir: "./e2e",
  use: { baseURL: process.env.E2E_BASE_URL ?? "http://localhost:5173" },
  reporter: [["list"], ["html", { open: "never" }]],
});
