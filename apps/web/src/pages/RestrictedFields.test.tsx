import type { Layer, MapFeature, Project } from "@spatial/map-core";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fakeBackend, makeMe } from "../test/fakeBackend";
import { renderApp, signedIn } from "../test/render";

vi.mock("../components/map/MapView", () => ({ MapView: () => <div data-testid="map" />, GEOJSON_LIMIT: 2000 }));

beforeEach(() => localStorage.clear());

const crsBrief = { id: 1, code: "EPSG:2136", name: "Accra / Ghana National Grid", units: "Gold Coast foot", kind: "projected" as const };
const project = { id: 5, name: "Kasoa local plan", community: "", description: "", crs: 1, crs_detail: crsBrief, status: "draft", layer_count: 1, created_at: "", updated_at: "" } as unknown as Project;
const layer = {
  id: 1,
  project: 5,
  name: "Parcels",
  domain: "B",
  geometry_type: "polygon",
  crs: 1,
  crs_detail: crsBrief,
  schema: [
    { name: "parcel_id", label: "Parcel id", type: "text", required: false },
    { name: "owner", label: "Owner", type: "text", required: false, sensitive: true },
  ],
  style: { kind: "single", fill: "#3a7d44", stroke: "#1d3d22", stroke_width: 1.5, point_radius: 5, fill_opacity: 0.4, label_field: null },
  order: 1,
  visible: true,
  opacity: 1,
  source: "drawn",
  feature_count: 1,
  created_at: "",
  updated_at: "",
} as unknown as Layer;

function feature(restricted: boolean): MapFeature {
  return {
    type: "Feature",
    id: 42,
    geometry: null,
    properties: restricted ? { parcel_id: "P-1" } : { parcel_id: "P-1", owner: "Ama Mensah" },
    meta: { uuid: "u", version: 1, origin: "drawn", verified: false, updated_at: "", restricted: restricted ? ["owner"] : [] },
  };
}

function backend(restricted: boolean, extra: Parameters<typeof fakeBackend>[0] = {}) {
  return fakeBackend({
    "GET /api/auth/me/": () => ({ body: makeMe() }),
    "GET /api/crs/systems/": () => ({ body: [] }),
    "GET /api/projects/5/": () => ({ body: project }),
    "GET /api/layers/": () => ({ body: [layer] }),
    "GET /api/basemaps/": () => ({ body: [] }),
    "GET /api/projects/5/boundary/": () => ({ body: { exists: false } }),
    "GET /api/layers/1/features/": () => ({ body: { type: "FeatureCollection", crs_code: "EPSG:4326", numberMatched: 1, numberReturned: 1, next_offset: null, features: [feature(restricted)] } }),
    ...extra,
  });
}

describe("restricted fields", () => {
  it("shows 'restricted' in place of a value the user's role may not see", async () => {
    renderApp(backend(true).fetch, { tokens: signedIn, route: "/projects/5" });
    await userEvent.click(await screen.findByRole("button", { name: "Parcels", exact: true }));
    const table = await screen.findByRole("region", { name: "Attributes of Parcels" });
    const row = (await within(table).findByRole("cell", { name: "P-1" })).closest("tr")!;
    expect(within(row).getByText("restricted")).toBeInTheDocument();
    expect(table).not.toHaveTextContent("Ama Mensah");
  });

  it("shows the value to those who may see it", async () => {
    renderApp(backend(false).fetch, { tokens: signedIn, route: "/projects/5" });
    await userEvent.click(await screen.findByRole("button", { name: "Parcels", exact: true }));
    const table = await screen.findByRole("region", { name: "Attributes of Parcels" });
    expect(await within(table).findByRole("cell", { name: "Ama Mensah" })).toBeInTheDocument();
  });

  it("marks a field restricted in the field editor, which also makes it optional", async () => {
    const api = backend(false, { "PATCH /api/layers/1/": (body) => ({ body: { ...layer, ...(body as object) } }) });
    renderApp(api.fetch, { tokens: signedIn, route: "/projects/5" });
    const tree = await screen.findByRole("region", { name: "B. Land & parcels" });
    await userEvent.click(within(tree).getByRole("button", { name: "Fields" }));
    const dialog = await screen.findByRole("dialog", { name: "Edit fields" });
    expect(within(dialog).getByLabelText("Field 2 restricted")).toBeChecked();
    expect(within(dialog).getByLabelText("Field 2 required")).toBeDisabled();
    await userEvent.click(within(dialog).getByLabelText("Field 1 restricted"));
    await userEvent.click(within(dialog).getByRole("button", { name: "Save fields" }));
    await waitFor(() => expect(api.calls.some((c) => c.method === "PATCH")).toBe(true));
    const sent = (api.calls.find((c) => c.method === "PATCH")!.body as { schema: { name: string; sensitive?: boolean }[] }).schema;
    expect(sent.map((f) => [f.name, Boolean(f.sensitive)])).toEqual([["parcel_id", true], ["owner", true]]);
  });
});
