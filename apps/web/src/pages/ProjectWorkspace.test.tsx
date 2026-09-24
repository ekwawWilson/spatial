import type { Layer, MapFeature, Project } from "@spatial/map-core";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { parseCell } from "../components/workspace/AttributeTable";
import { emptyPage, fakeBackend, makeMe } from "../test/fakeBackend";
import { renderApp, signedIn } from "../test/render";

// OpenLayers needs a real canvas; the map itself is covered by the Playwright tests.
vi.mock("../components/map/MapView", () => ({ MapView: () => <div data-testid="map" />, GEOJSON_LIMIT: 2000 }));

beforeEach(() => localStorage.clear());

const crsBrief = { id: 1, code: "EPSG:2136", name: "Accra / Ghana National Grid", units: "Gold Coast foot", kind: "projected" as const };

const project: Project = {
  id: 5,
  name: "Kasoa local plan",
  community: "Kasoa",
  description: "",
  crs: 1,
  crs_detail: crsBrief,
  status: "draft",
  layer_count: 2,
  created_at: "",
  updated_at: "",
};

const baseStyle = { kind: "single" as const, fill: "#3a7d44", stroke: "#1d3d22", stroke_width: 1.5, point_radius: 5, fill_opacity: 0.4, label_field: null };

function layer(id: number, name: string, extra: Partial<Layer> = {}): Layer {
  return {
    id,
    project: 5,
    name,
    domain: "B",
    geometry_type: "polygon",
    crs: 1,
    crs_detail: crsBrief,
    schema: [
      { name: "parcel_id", label: "Parcel id", type: "text", required: true },
      { name: "floors", label: "Floors", type: "integer", required: false },
      { name: "use", label: "Use", type: "choice", required: false, choices: ["residential", "commercial"] },
    ],
    style: baseStyle,
    order: 10 - id,
    visible: true,
    opacity: 1,
    source: "drawn",
    feature_count: 1,
    created_at: "",
    updated_at: "",
    ...extra,
  };
}

const feature: MapFeature = {
  type: "Feature",
  id: 42,
  geometry: null,
  properties: { parcel_id: "P-1", floors: 2, use: "residential" },
  meta: { uuid: "u", version: 3, origin: "drawn", verified: false, updated_at: "" },
};

function backend(overrides: Parameters<typeof fakeBackend>[0] = {}) {
  return fakeBackend({
    "GET /api/auth/me/": () => ({ body: makeMe() }),
    "GET /api/crs/systems/": () => ({ body: [] }),
    "GET /api/crs/defaults/": () => ({ body: { system: crsBrief, district: null, user: null, effective: { crs: crsBrief, source: "system" } } }),
    "GET /api/projects/": () => ({ body: { ...emptyPage, count: 1, results: [project] } }),
    "GET /api/projects/5/": () => ({ body: project }),
    "GET /api/layers/": () => ({ body: [layer(1, "Parcels"), layer(2, "Buildings", { domain: "C" })] }),
    "GET /api/layers/1/features/": () => ({ body: { type: "FeatureCollection", crs_code: "EPSG:4326", numberMatched: 1, numberReturned: 1, next_offset: null, features: [feature] } }),
    ...overrides,
  });
}

describe("projects page", () => {
  it("lists projects and shows the default coordinate system for new ones", async () => {
    renderApp(backend().fetch, { tokens: signedIn, route: "/projects" });
    expect(await screen.findByRole("link", { name: "Kasoa local plan" })).toBeInTheDocument();
    expect(await screen.findByRole("option", { name: /Default: EPSG:2136 \(system default\)/ })).toBeInTheDocument();
  });

  it("creates a project and opens it", async () => {
    const api = backend({ "POST /api/projects/": () => ({ status: 201, body: project }) });
    renderApp(api.fetch, { tokens: signedIn, route: "/projects" });
    const form = await screen.findByRole("form", { name: "New project" });
    await userEvent.type(within(form).getByLabelText("Name"), "Kasoa local plan");
    await userEvent.click(within(form).getByRole("button", { name: "Create project" }));
    expect(await screen.findByRole("heading", { name: "Kasoa local plan" })).toBeInTheDocument();
    expect(api.calls.find((c) => c.method === "POST")?.body).toEqual({ name: "Kasoa local plan", community: "" });
  });
});

describe("layer tree", () => {
  it("groups layers by data domain", async () => {
    renderApp(backend().fetch, { tokens: signedIn, route: "/projects/5" });
    expect(await screen.findByRole("region", { name: "B. Land & parcels" })).toHaveTextContent("Parcels");
    expect(screen.getByRole("region", { name: "C. Buildings & properties" })).toHaveTextContent("Buildings");
  });

  it("moving a layer sends the whole new order", async () => {
    const api = backend({ "POST /api/projects/5/layer-order/": () => ({ status: 204 }) });
    renderApp(api.fetch, { tokens: signedIn, route: "/projects/5" });
    await userEvent.click(await screen.findByRole("button", { name: "Move Buildings up" }));
    await waitFor(() => expect(api.calls.some((c) => c.path === "/api/projects/5/layer-order/")).toBe(true));
    expect(api.calls.find((c) => c.path === "/api/projects/5/layer-order/")?.body).toEqual({ layer_ids: [2, 1] });
  });

  it("hiding a layer saves its visibility", async () => {
    const api = backend({ "PATCH /api/layers/1/": (body) => ({ body: { ...layer(1, "Parcels"), ...(body as object) } }) });
    renderApp(api.fetch, { tokens: signedIn, route: "/projects/5" });
    await userEvent.click(await screen.findByRole("checkbox", { name: "Show Parcels" }));
    await waitFor(() => expect(api.calls.find((c) => c.method === "PATCH")?.body).toEqual({ visible: false }));
  });

  it("viewers get no editing controls", async () => {
    localStorage.setItem("spatial.district.1", "20"); // Ama is a viewer there
    renderApp(backend().fetch, { tokens: signedIn, route: "/projects/5" });
    await screen.findByRole("region", { name: "B. Land & parcels" });
    expect(screen.queryByRole("button", { name: "Move Buildings up" })).not.toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Add layer" })).not.toBeInTheDocument();
  });
});

describe("attribute table", () => {
  async function openTable(api: ReturnType<typeof backend>) {
    renderApp(api.fetch, { tokens: signedIn, route: "/projects/5" });
    await userEvent.click(await screen.findByRole("button", { name: "Parcels" }));
    return screen.findByRole("region", { name: "Attributes of Parcels" });
  }

  it("edits a value with the feature's version and converts numbers", async () => {
    const api = backend({ "PATCH /api/features/42/": () => ({ body: { ...feature, meta: { ...feature.meta, version: 4 } } }) });
    const table = await openTable(api);
    await userEvent.dblClick(await within(table).findByRole("cell", { name: "2" }));
    const input = within(table).getByLabelText("Floors of feature 42");
    await userEvent.clear(input);
    await userEvent.type(input, "3{enter}");
    await waitFor(() =>
      expect(api.calls.find((c) => c.method === "PATCH")?.body).toEqual({ version: 3, properties: { floors: 3 } }),
    );
    expect(await within(table).findByRole("status")).toHaveTextContent("Saved Floors.");
  });

  it("explains a conflict when someone else saved first", async () => {
    const api = backend({
      "PATCH /api/features/42/": () => ({ status: 409, body: { detail: "Someone else changed this feature since you loaded it.", current: feature } }),
    });
    const table = await openTable(api);
    await userEvent.dblClick(await within(table).findByRole("cell", { name: "2" }));
    await userEvent.type(within(table).getByLabelText("Floors of feature 42"), "{enter}");
    expect(await within(table).findByRole("alert")).toHaveTextContent("Someone else changed this feature");
  });

  it("shows the server's validation message", async () => {
    const api = backend({ "PATCH /api/features/42/": () => ({ status: 400, body: { floors: ["must be a whole number"] } }) });
    const table = await openTable(api);
    await userEvent.dblClick(await within(table).findByRole("cell", { name: "2" }));
    const input = within(table).getByLabelText("Floors of feature 42");
    await userEvent.clear(input);
    await userEvent.type(input, "two{enter}");
    expect(await within(table).findByRole("alert")).toHaveTextContent("must be a whole number");
  });

  it("parses typed values by field type", () => {
    expect(parseCell({ name: "n", label: "n", type: "integer", required: false }, " 12 ")).toBe(12);
    expect(parseCell({ name: "b", label: "b", type: "boolean", required: false }, "Yes")).toBe(true);
    expect(parseCell({ name: "t", label: "t", type: "text", required: false }, "  ")).toBeNull();
  });
});

describe("layer editors", () => {
  it("colouring by a choice field makes one category per choice", async () => {
    const api = backend({ "PATCH /api/layers/1/": (body) => ({ body: { ...layer(1, "Parcels"), ...(body as object) } }) });
    renderApp(api.fetch, { tokens: signedIn, route: "/projects/5" });
    const tree = await screen.findByRole("region", { name: "B. Land & parcels" });
    await userEvent.click(within(tree).getByRole("button", { name: "Style" }));
    const dialog = await screen.findByRole("dialog", { name: "Edit style" });
    await userEvent.selectOptions(within(dialog).getByLabelText("Colour by"), "use");
    expect(within(dialog).getByRole("group", { name: "residential" })).toBeInTheDocument();
    expect(within(dialog).getByRole("group", { name: "commercial" })).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Save style" }));
    const style = (api.calls.find((c) => c.method === "PATCH")?.body as { style: { kind: string; field: string; categories: unknown[] } }).style;
    expect(style).toMatchObject({ kind: "categorized", field: "use" });
    expect(style.categories).toHaveLength(2);
  });

  it("removing a field that holds values asks for confirmation, then sends it", async () => {
    let attempts = 0;
    const api = backend({
      "PATCH /api/layers/1/": () => {
        attempts += 1;
        return attempts === 1
          ? { status: 400, body: { schema: ["Removing 'floors' would delete its value from 1 feature(s). Confirm with ?confirm_drop=floors."] } }
          : { body: layer(1, "Parcels") };
      },
    });
    renderApp(api.fetch, { tokens: signedIn, route: "/projects/5" });
    const tree = await screen.findByRole("region", { name: "B. Land & parcels" });
    await userEvent.click(within(tree).getByRole("button", { name: "Fields" }));
    const dialog = await screen.findByRole("dialog", { name: "Edit fields" });
    await userEvent.click(within(dialog).getAllByRole("button", { name: "Remove" })[1]!);
    await userEvent.click(within(dialog).getByRole("button", { name: "Save fields" }));
    expect(await within(dialog).findByText(/permanently delete the values of floors/)).toBeInTheDocument();
    await userEvent.click(within(dialog).getByRole("button", { name: "Delete values and save" }));
    await waitFor(() => expect(api.calls.filter((c) => c.method === "PATCH")).toHaveLength(2));
    expect(api.calls.filter((c) => c.method === "PATCH")[1]?.path).toBe("/api/layers/1/?confirm_drop=floors");
  });
});
