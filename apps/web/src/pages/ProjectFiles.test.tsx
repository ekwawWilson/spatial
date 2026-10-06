import type { Project, SppReport } from "@spatial/map-core";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { emptyPage, fakeBackend, makeMe } from "../test/fakeBackend";
import { renderApp, signedIn } from "../test/render";

vi.mock("../components/map/MapView", () => ({ MapView: () => <div data-testid="map" />, GEOJSON_LIMIT: 2000 }));

beforeEach(() => localStorage.clear());

const crsBrief = { id: 1, code: "EPSG:2136", name: "Accra / Ghana National Grid", units: "Gold Coast foot", kind: "projected" as const };
const project = {
  id: 5,
  name: "Kasoa local plan",
  community: "Kasoa",
  description: "",
  crs: 1,
  crs_detail: crsBrief,
  status: "draft",
  layer_count: 0,
  created_at: "",
  updated_at: "",
} as unknown as Project;

const report: SppReport = {
  project: 9,
  name: "Kasoa local plan (2)",
  renamed_from: "Kasoa local plan",
  from_district: "Awutu Senya East",
  saved_at: "2026-10-01T09:00:00+00:00",
  saved_by: "ama@example.test",
  layers: 3,
  features: 120,
  history_entries: 300,
  checklist_items: 22,
  attachments: 1,
  new_feature_ids: 0,
  crs_added: [],
  basemaps_added: [],
  basemaps_skipped: ["Assembly drone tiles"],
};

function backend(extra: Parameters<typeof fakeBackend>[0] = {}) {
  return fakeBackend({
    "GET /api/auth/me/": () => ({ body: makeMe() }),
    "GET /api/crs/systems/": () => ({ body: [] }),
    "GET /api/crs/defaults/": () => ({ body: { system: crsBrief, district: null, user: null, effective: { crs: crsBrief, source: "system" } } }),
    "GET /api/projects/": () => ({ body: { ...emptyPage, count: 1, results: [project] } }),
    "GET /api/projects/5/": () => ({ body: project }),
    "GET /api/layers/": () => ({ body: [] }),
    "GET /api/basemaps/": () => ({ body: [] }),
    "GET /api/projects/5/boundary/": () => ({ body: { exists: false } }),
    ...extra,
  });
}

const file = () => new File([new Uint8Array([0x89, 0x53, 0x50, 0x50])], "kasoa.spp", { type: "application/octet-stream" });

describe("opening a .spp file", () => {
  it("uploads the file and reports what was created", async () => {
    const api = backend({ "POST /api/spp/open/": () => ({ status: 201, body: report }) });
    renderApp(api.fetch, { tokens: signedIn, route: "/projects" });
    const section = await screen.findByRole("region", { name: "Open a project file" });
    await userEvent.upload(within(section).getByLabelText("Project file"), file());
    const result = await within(section).findByRole("status", { name: "Opened project" });
    expect(within(result).getByRole("link", { name: "Kasoa local plan (2)" })).toHaveAttribute("href", "/projects/9");
    expect(result).toHaveTextContent("3 layers, 120 features, 22 checklist items, 1 document.");
    expect(result).toHaveTextContent('already exists here, so this copy is named "Kasoa local plan (2)"');
    expect(result).toHaveTextContent("Saved by ama@example.test in Awutu Senya East on 2026-10-01.");
    expect(result).toHaveTextContent("Basemaps not added (a district administrator can add them): Assembly drone tiles.");
    const call = api.calls.find((c) => c.path === "/api/spp/open/");
    expect((call?.body as FormData).get("file")).toBeInstanceOf(File);
  });

  it("explains why a file can't be opened", async () => {
    const message = "This file is protected with the organisation key 'other', which this server doesn't have.";
    const api = backend({ "POST /api/spp/open/": () => ({ status: 400, body: { file: message } }) });
    renderApp(api.fetch, { tokens: signedIn, route: "/projects" });
    const section = await screen.findByRole("region", { name: "Open a project file" });
    await userEvent.upload(within(section).getByLabelText("Project file"), file());
    expect(await within(section).findByText(/organisation key 'other', which this server doesn't have/)).toBeInTheDocument();
  });
});

describe("saving a project as .spp", () => {
  it("asks the server for the file and saves it under the server's name", async () => {
    const created = vi.fn(() => "blob:test");
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: created, revokeObjectURL: vi.fn() }));
    const api = backend({ "POST /api/projects/5/spp/": () => ({ body: {} }) });
    renderApp(api.fetch, { tokens: signedIn, route: "/projects/5" });
    await userEvent.click(await screen.findByRole("button", { name: "Save as .spp" }));
    await waitFor(() => expect(created).toHaveBeenCalled());
    expect(api.calls.some((c) => c.method === "POST" && c.path === "/api/projects/5/spp/")).toBe(true);
  });
});
