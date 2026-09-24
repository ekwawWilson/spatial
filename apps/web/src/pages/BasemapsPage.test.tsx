import type { Basemap } from "@spatial/map-core";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fakeBackend, makeMe } from "../test/fakeBackend";
import { renderApp, signedIn } from "../test/render";

vi.mock("../components/map/MapView", () => ({ MapView: () => <div data-testid="map" />, GEOJSON_LIMIT: 2000 }));

beforeEach(() => localStorage.clear());

function basemap(id: number, name: string, extra: Partial<Basemap> = {}): Basemap {
  return {
    id,
    name,
    kind: "xyz",
    preset: "",
    url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    layers: "",
    attribution: "",
    min_zoom: 0,
    max_zoom: 19,
    requires_key: false,
    has_key: false,
    offline_cache_allowed: false,
    notes: "",
    is_active: true,
    order: 0,
    scope: "global",
    ...extra,
  };
}

const osm = basemap(1, "OpenStreetMap", { preset: "osm" });
const google = basemap(2, "Google Maps (satellite)", { kind: "google", preset: "google_satellite", requires_key: true });

function backend(extra: Parameters<typeof fakeBackend>[0] = {}) {
  return fakeBackend({
    "GET /api/auth/me/": () => ({ body: makeMe() }),
    "GET /api/basemaps/": () => ({ body: [osm, google] }),
    ...extra,
  });
}

describe("basemaps page", () => {
  it("adds a ready-made basemap with its key", async () => {
    const api = backend({ "POST /api/basemaps/presets/": () => ({ status: 201, body: google }) });
    renderApp(api.fetch, { tokens: signedIn, route: "/basemaps" });
    const form = await screen.findByRole("form", { name: "Add a ready-made basemap" });
    await userEvent.type(within(form).getByLabelText("API key"), "MY-KEY");
    await userEvent.click(within(form).getByRole("button", { name: "Add" }));
    await waitFor(() =>
      expect(api.calls.find((c) => c.method === "POST")?.body).toEqual({
        preset: "google_satellite",
        api_key: "MY-KEY",
        scope: "district",
      }),
    );
    expect(await screen.findByRole("status")).toHaveTextContent("Basemap added.");
  });

  it("shows which sources lack a key and never shows keys", async () => {
    renderApp(backend().fetch, { tokens: signedIn, route: "/basemaps" });
    const row = (await screen.findByRole("cell", { name: "Google Maps (satellite)" })).closest("tr")!;
    expect(row).toHaveTextContent("Missing");
    expect(row).toHaveTextContent("Not allowed");
  });

  it("marking a custom source as allowed offline sends the flag", async () => {
    const api = backend({ "POST /api/basemaps/": () => ({ status: 201, body: osm }) });
    renderApp(api.fetch, { tokens: signedIn, route: "/basemaps" });
    const form = await screen.findByRole("form", { name: "Add your own basemap" });
    await userEvent.type(within(form).getByLabelText("Basemap name"), "Drone mosaic");
    await userEvent.type(within(form).getByLabelText("Service URL"), "https://tiles.example.gov.gh/{{z}/{{x}/{{y}.png");
    await userEvent.click(within(form).getByRole("checkbox"));
    await userEvent.click(within(form).getByRole("button", { name: "Add basemap" }));
    await waitFor(() =>
      expect(api.calls.find((c) => c.method === "POST")?.body).toMatchObject({
        name: "Drone mosaic",
        url: "https://tiles.example.gov.gh/{z}/{x}/{y}.png",
        offline_cache_allowed: true,
      }),
    );
  });

  it("viewers don't get the management forms", async () => {
    localStorage.setItem("spatial.district.1", "20");
    renderApp(backend().fetch, { tokens: signedIn, route: "/basemaps" });
    await screen.findByRole("cell", { name: "OpenStreetMap" });
    expect(screen.queryByRole("form", { name: "Add a ready-made basemap" })).not.toBeInTheDocument();
  });
});

describe("basemap picker in a project", () => {
  it("explains a missing key instead of showing a blank map", async () => {
    const crs = { id: 1, code: "EPSG:2136", name: "Ghana National Grid", units: "Gold Coast foot", kind: "projected" as const };
    const api = backend({
      "GET /api/crs/systems/": () => ({ body: [] }),
      "GET /api/projects/5/": () => ({
        body: { id: 5, name: "Plan", community: "", description: "", crs: 1, crs_detail: crs, status: "draft", layer_count: 0, created_at: "", updated_at: "" },
      }),
      "GET /api/layers/": () => ({ body: [] }),
      "GET /api/basemaps/1/client-config/": () => ({ body: { ...osm, kind: "xyz" } }),
      "GET /api/basemaps/2/client-config/": () => ({
        status: 400,
        body: { detail: ["Google Maps (satellite) needs an API key. Ask an administrator to add one on the Basemaps page."] },
      }),
    });
    renderApp(api.fetch, { tokens: signedIn, route: "/projects/5" });
    const picker = await screen.findByRole("region", { name: "Basemap" });
    // The first available basemap is chosen once the list has loaded.
    await waitFor(() => expect(within(picker).getByRole("combobox")).toHaveValue("1"));
    await userEvent.selectOptions(within(picker).getByRole("combobox"), "2");
    expect(await within(picker).findByRole("alert")).toHaveTextContent("needs an API key");
    expect(localStorage.getItem("spatial.basemap.5")).toBe("2");
  });
});
