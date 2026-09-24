import type { CoordinateSystem, DataJob, Layer } from "@spatial/map-core";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { emptyPage, fakeBackend, makeMe } from "../../test/fakeBackend";
import { renderApp, signedIn } from "../../test/render";

vi.mock("../map/MapView", () => ({ MapView: () => <div />, GEOJSON_LIMIT: 2000 }));

it("preselects the file's CRS even when the system list arrives after the upload", async () => {
  const grid = { id: 1, code: "EPSG:2136", name: "Accra / Ghana National Grid", units: "Gold Coast foot", kind: "projected", scope: "builtin" } as CoordinateSystem;
  const job = {
    id: 9, uuid: "u", kind: "import", project: 5, status: "inspected", file_format: "shp_zip", original_name: "b.zip",
    inspection: { format: "shp_zip", crs_confirmation_required: false, layers: [{ name: "buildings", feature_count: 6, geometry_types: { Polygon: 6 }, has_z: false, fields: [], crs: { found: true, epsg: 2136, confidence: 100, name: "Accra", wkt: null }, encoding: "UTF-8", cad_layers: [] }] },
    plan: {}, live_progress: null, report: {}, error: "", result_name: "", download_url: null, created_at: "", finished_at: null,
  } as unknown as DataJob;
  let uploaded = false;
  const api = fakeBackend({
    "GET /api/auth/me/": () => ({ body: makeMe() }),
    // Empty until the upload has happened: the list arrives late.
    "GET /api/crs/systems/": () => ({ body: uploaded ? [grid] : [] }),
    "GET /api/projects/5/": () => ({ body: { id: 5, name: "P", community: "", description: "", crs: 1, crs_detail: grid, status: "draft", layer_count: 0, created_at: "", updated_at: "" } }),
    "GET /api/layers/": () => ({ body: [] as Layer[] }),
    "GET /api/basemaps/": () => ({ body: [] }),
    "GET /api/transfer/jobs/": () => ({ body: emptyPage }),
    "POST /api/transfer/jobs/imports/": () => {
      uploaded = true;
      return { status: 201, body: job };
    },
  });
  renderApp(api.fetch, { tokens: signedIn, route: "/projects/5" });
  await userEvent.click(await screen.findByRole("button", { name: "Import data" }));
  const dialog = screen.getByRole("dialog", { name: "Import data" });
  await userEvent.upload(within(dialog).getByLabelText("File", { exact: true }), new File(["z"], "b.zip"));
  await userEvent.click(within(dialog).getByRole("button", { name: "Upload and inspect" }));
  const select = await within(dialog).findByLabelText("Coordinate system of buildings");
  expect(select).toHaveValue(""); // no systems known yet
  // Switching district reloads the system list (now including EPSG:2136).
  await userEvent.selectOptions(screen.getAllByRole("combobox")[0]!, "Other District Assembly");
  await userEvent.selectOptions(screen.getAllByRole("combobox")[0]!, "Sample Municipal Assembly");
  await waitFor(() => expect(within(dialog).getByLabelText("Coordinate system of buildings")).toHaveValue("EPSG:2136"));
});
