import type { Imagery } from "@spatial/map-core";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { fakeBackend, makeMe } from "../test/fakeBackend";
import { renderApp, signedIn } from "../test/render";

beforeEach(() => localStorage.clear());

function image(id: number, extra: Partial<Imagery> = {}): Imagery {
  return {
    id,
    project: 5,
    name: `Image ${id}`,
    kind: "ortho",
    status: "ready",
    error: "",
    original_name: "flight.tif",
    capture_date: "2026-09-01",
    source: "Assembly drone team",
    crs: "EPSG:32630 WGS 84 / UTM zone 30N",
    width: 20000,
    height: 20000,
    bands: 3,
    resolution_m: 0.05,
    bounds: [-0.3, 5.5, -0.2, 5.6],
    value_range: null,
    min_zoom: 12,
    max_zoom: 22,
    size_bytes: 300 * 1024 * 1024,
    basemap: 9,
    tile_url: `/api/imagery/${id}/tiles/{z}/{x}/{y}.png`,
    created_at: "",
    ...extra,
  };
}

function backend(images: Imagery[], extra: Parameters<typeof fakeBackend>[0] = {}) {
  return fakeBackend({
    "GET /api/auth/me/": () => ({ body: makeMe() }),
    "GET /api/imagery/": () => ({ body: images }),
    "GET /api/crs/systems/": () => ({ body: [] }),
    ...extra,
  });
}

describe("imagery page", () => {
  it("lists images with what a planner needs to judge them", async () => {
    const failed = image(2, { name: "Bad file", status: "failed", error: "The image isn't georeferenced: it doesn't say where on the ground it is.", resolution_m: null, size_bytes: 0, crs: "" });
    renderApp(backend([image(1, { name: "Kasoa flight" }), failed]).fetch, { tokens: signedIn, route: "/projects/5/imagery" });
    const row = (await screen.findByText("Kasoa flight")).closest("tr")!;
    expect(row).toHaveTextContent("Orthophoto");
    expect(row).toHaveTextContent("Ready");
    expect(row).toHaveTextContent("5.0 cm");
    expect(row).toHaveTextContent("300.0 MB");
    expect(within(row).getByLabelText("Capture date of Kasoa flight")).toHaveValue("2026-09-01");
    expect(screen.getByRole("alert")).toHaveTextContent("isn't georeferenced");
  });

  it("uploads a GeoTIFF in pieces, then its details", async () => {
    const api = backend([], {
      "POST /api/imagery/uploads/": () => ({ status: 201, body: { id: "u1", file_name: "june.tif", size: 1, received: 0, chunk_size: 8 * 1024 * 1024 } }),
      "PUT /api/imagery/uploads/u1/chunk/": () => ({ body: { id: "u1", file_name: "june.tif", size: 1, received: 1, chunk_size: 8 * 1024 * 1024 } }),
      "POST /api/imagery/uploads/u1/finish/": () => ({ status: 201, body: image(3, { status: "queued" }) }),
    });
    renderApp(api.fetch, { tokens: signedIn, route: "/projects/5/imagery" });
    const form = await screen.findByRole("form", { name: "Upload imagery" });
    await userEvent.upload(within(form).getByLabelText("GeoTIFF file"), new File(["x"], "june.tif", { type: "image/tiff" }));
    await userEvent.selectOptions(within(form).getByLabelText("Kind"), "dem");
    await userEvent.type(within(form).getByLabelText("Captured on"), "2026-06-15");
    await userEvent.click(within(form).getByRole("button", { name: "Upload" }));
    expect(await screen.findByText(/being checked and converted/)).toBeInTheDocument();
    const call = (method: string, path: string) => api.calls.find((c) => c.method === method && c.path.startsWith(path));
    expect(call("POST", "/api/imagery/uploads/")?.body).toEqual({ file_name: "june.tif", size: 1 });
    const piece = call("PUT", "/api/imagery/uploads/u1/chunk/")!;
    expect(piece.path).toBe("/api/imagery/uploads/u1/chunk/?offset=0");
    expect(piece.body).toBeInstanceOf(Blob);
    // Read from the file unless chosen: no crs.
    expect(call("POST", "/api/imagery/uploads/u1/finish/")?.body).toEqual({ project: 5, kind: "dem", capture_date: "2026-06-15" });
  });

  it("makes contours from an elevation model", async () => {
    const dem = image(4, { name: "Kasoa DEM", kind: "dem", basemap: null, value_range: [10, 80] });
    const api = backend([dem], {
      "POST /api/imagery/4/contours/": () => ({ status: 201, body: { layer: 12, layer_name: "Topography (contours)", contours: 40, replaced: 0, interval: 2, converted_from: "EPSG:32630" } }),
    });
    renderApp(api.fetch, { tokens: signedIn, route: "/projects/5/imagery" });
    const interval = await screen.findByLabelText("Contour interval for Kasoa DEM");
    await userEvent.clear(interval);
    await userEvent.type(interval, "2");
    await userEvent.click(screen.getByRole("button", { name: "Make contours" }));
    await waitFor(() => expect(api.calls.find((c) => c.method === "POST")?.body).toEqual({ interval: 2 }));
    expect(await screen.findByRole("status")).toHaveTextContent('Contours made in the layer "Topography (contours)".');
  });

  it("is read-only for viewers", async () => {
    const me = makeMe();
    me.memberships[0]!.permissions = ["project.view", "district.view"];
    renderApp(backend([image(1)], { "GET /api/auth/me/": () => ({ body: me }) }).fetch, { tokens: signedIn, route: "/projects/5/imagery" });
    expect(await screen.findByText("Image 1")).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Upload imagery" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete Image 1" })).not.toBeInTheDocument();
  });
});
