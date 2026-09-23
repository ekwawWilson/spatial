import type { ApiClient, HealthReport } from "@spatial/map-core";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { App } from "./App";

const report: HealthReport = {
  ok: false,
  database: { ok: true, postgis: "3.5.2" },
  gdal: { ok: false, version: "3.10.3", missing_drivers: ["LIBKML"] },
  redis: { ok: true },
};

const fakeApi = (impl: ApiClient["getHealth"]): ApiClient => ({ getHealth: impl });

describe("App status page", () => {
  it("names the failing service and its problem", async () => {
    render(<App api={fakeApi(() => Promise.resolve(report))} />);
    expect(await screen.findByRole("status")).toHaveTextContent("Some services are failing");
    expect(screen.getByText("Missing drivers: LIBKML")).toBeInTheDocument();
  });

  it("shows an error when the API is unreachable", async () => {
    render(<App api={fakeApi(() => Promise.reject(new Error("network down")))} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("network down");
  });
});
