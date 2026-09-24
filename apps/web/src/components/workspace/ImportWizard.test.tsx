import type { CoordinateSystem, DataJob, InspectedLayer, Inspection, Layer } from "@spatial/map-core";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { emptyPage, fakeBackend, makeMe } from "../../test/fakeBackend";
import { renderApp, signedIn } from "../../test/render";
import { choiceProblem, defaultChoice, dominantFamily } from "./ImportWizard";

vi.mock("../map/MapView", () => ({ MapView: () => <div data-testid="map" />, GEOJSON_LIMIT: 2000 }));

beforeEach(() => localStorage.clear());

const grid = { id: 1, code: "EPSG:2136", name: "Accra / Ghana National Grid", units: "Gold Coast foot", kind: "projected" } as CoordinateSystem;
const wgs = { id: 2, code: "EPSG:4326", name: "WGS 84", units: "degree", kind: "geographic" } as CoordinateSystem;

function source(extra: Partial<InspectedLayer> = {}): InspectedLayer {
  return {
    name: "parcels",
    feature_count: 6,
    geometry_types: { Polygon: 5, MultiPolygon: 1 },
    has_z: false,
    fields: [{ name: "PROPERTY_I", suggested_name: "property_id", type: "text" }],
    crs: { found: true, epsg: 2136, confidence: 100, name: "Accra / Ghana National Grid", wkt: null },
    encoding: "UTF-8",
    cad_layers: [],
    ...extra,
  };
}

const inspection = (layers: InspectedLayer[], confirm = false): Inspection => ({
  format: "shp_zip",
  layers,
  crs_confirmation_required: confirm,
});

describe("default choices", () => {
  it("uses the file's CRS when it's available here, and suggested field names", () => {
    const choice = defaultChoice(source(), inspection([source()]), [grid, wgs]);
    expect(choice.plan.crs).toBe("EPSG:2136");
    expect(choice.plan.crs_confirmed).toBe(true);
    expect(choice.plan.new_layer?.geometry_type).toBe("polygon");
    expect(choice.plan.fields).toEqual([{ source: "PROPERTY_I", target: "property_id", type: "text" }]);
    expect(choiceProblem(choice, source(), inspection([source()]))).toBeNull();
  });

  it("makes the user choose and confirm when the file has no CRS", () => {
    const noCrs = source({ crs: { found: false, epsg: null, confidence: 0, name: null, wkt: null } });
    const choice = defaultChoice(noCrs, inspection([noCrs]), [grid]);
    expect(choice.plan.crs).toBe("");
    expect(choiceProblem(choice, noCrs, inspection([noCrs]))).toMatch(/Choose the coordinate system/);
    choice.plan.crs = "EPSG:2136";
    expect(choiceProblem(choice, noCrs, inspection([noCrs]))).toMatch(/doesn't say which coordinate system/);
    choice.plan.crs_confirmed = true;
    expect(choiceProblem(choice, noCrs, inspection([noCrs]))).toBeNull();
  });

  it("CAD and CSV files always need confirmation", () => {
    const cad = source({ name: "entities", cad_layers: ["parcels", "roads"] });
    const choice = defaultChoice(cad, inspection([cad], true), [grid]);
    expect(choice.plan.crs_confirmed).toBe(false);
    expect(choice.plan.cad_layers).toEqual(["parcels", "roads"]);
  });

  it("picks the most common geometry family", () => {
    expect(dominantFamily(source({ geometry_types: { LineString: 3, Point: 1 } }))).toBe("line");
  });
});

describe("import wizard in a project", () => {
  const project = { id: 5, name: "Plan", community: "", description: "", crs: 1, crs_detail: grid, status: "draft", layer_count: 0, created_at: "", updated_at: "" };
  const inspected: DataJob = {
    id: 9,
    uuid: "u",
    kind: "import",
    project: 5,
    status: "inspected",
    file_format: "shp_zip",
    original_name: "parcels.zip",
    inspection: inspection([source({ crs: { found: false, epsg: null, confidence: 0, name: null, wkt: null } })]),
    plan: {},
    live_progress: null,
    report: {},
    error: "",
    result_name: "",
    download_url: null,
    created_at: "",
    finished_at: null,
  };

  function backend() {
    let polls = 0;
    return fakeBackend({
      "GET /api/auth/me/": () => ({ body: makeMe() }),
      "GET /api/crs/systems/": () => ({ body: [grid, wgs] }),
      "GET /api/projects/5/": () => ({ body: project }),
      "GET /api/layers/": () => ({ body: [] as Layer[] }),
      "GET /api/basemaps/": () => ({ body: [] }),
      "GET /api/transfer/jobs/": () => ({ body: emptyPage }),
      "POST /api/transfer/jobs/imports/": () => ({ status: 201, body: inspected }),
      "POST /api/transfer/jobs/9/run/": () => ({ status: 202, body: { ...inspected, status: "queued" } }),
      "GET /api/transfer/jobs/9/": () => {
        polls += 1;
        return {
          body:
            polls < 2
              ? { ...inspected, status: "running", live_progress: { done: 3, total: 6, stage: "Importing" } }
              : {
                  ...inspected,
                  status: "done",
                  report: {
                    layers: [
                      { source: "parcels", target_layer: 3, target_name: "parcels", imported: 5, skipped: 1, fixed_geometries: 0, duplicates: 0, blanked_values: 0, z_dropped: 0, operation: null, problems: [{ row: 4, message: "is invalid: Self-intersection" }] },
                    ],
                  },
                },
        };
      },
    });
  }

  it("won't import a file without a CRS until it's chosen and confirmed, then reports", async () => {
    const api = backend();
    renderApp(api.fetch, { tokens: signedIn, route: "/projects/5" });
    await userEvent.click(await screen.findByRole("button", { name: "Import data" }));
    const dialog = screen.getByRole("dialog", { name: "Import data" });
    await userEvent.upload(within(dialog).getByLabelText("File"), new File(["zip"], "parcels.zip"));
    await userEvent.click(within(dialog).getByRole("button", { name: "Upload and inspect" }));

    expect(await within(dialog).findByText("The file doesn't say which coordinate system it uses.")).toBeInTheDocument();
    const importButton = within(dialog).getByRole("button", { name: "Import" });
    expect(importButton).toBeDisabled();
    await userEvent.selectOptions(within(dialog).getByLabelText("Coordinate system of parcels"), "EPSG:2136");
    expect(importButton).toBeDisabled();
    await userEvent.click(within(dialog).getByLabelText("Confirm coordinate system of parcels"));
    expect(importButton).toBeEnabled();
    await userEvent.click(importButton);

    const run = api.calls.find((c) => c.path === "/api/transfer/jobs/9/run/");
    expect(run?.body).toMatchObject({
      layers: [{ source: "parcels", crs: "EPSG:2136", crs_confirmed: true, fields: [{ source: "PROPERTY_I", target: "property_id" }] }],
    });
    const report = await within(dialog).findByRole("region", { name: "Import report" }, { timeout: 5000 });
    expect(report).toHaveTextContent("5 imported, 1 skipped");
    expect(report).toHaveTextContent("1 row(s) with problems");
  });

  it("viewers get no import or export buttons", async () => {
    localStorage.setItem("spatial.district.1", "20");
    renderApp(backend().fetch, { tokens: signedIn, route: "/projects/5" });
    await screen.findByRole("region", { name: "Basemap" });
    expect(screen.queryByRole("button", { name: "Import data" })).not.toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("button", { name: "Export" })).not.toBeInTheDocument());
  });
});
