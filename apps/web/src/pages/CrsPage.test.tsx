import type { CoordinateSystem } from "@spatial/map-core";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { fakeBackend, makeMe } from "../test/fakeBackend";
import { renderApp, signedIn } from "../test/render";

beforeEach(() => localStorage.clear());

function crs(id: number, code: string, name: string, extra: Partial<CoordinateSystem> = {}): CoordinateSystem {
  return {
    id,
    code,
    name,
    srid: Number(code.split(":")[1]),
    kind: "projected",
    units: "metre",
    unit_to_metre: 1,
    area_of_use: "Ghana",
    bounds: null,
    notes: "",
    is_builtin: true,
    scope: "builtin",
    is_active: true,
    proj4: "",
    wkt: "",
    ...extra,
  };
}

const GRID = crs(1, "EPSG:2136", "Accra / Ghana National Grid", { units: "Gold Coast foot" });
const WGS = crs(2, "EPSG:4326", "WGS 84", { kind: "geographic", units: "degree", unit_to_metre: null });
const METRE = crs(3, "EPSG:25000", "Leigon / Ghana Metre Grid");

function backend(me = makeMe()) {
  return fakeBackend({
    "GET /api/auth/me/": () => ({ body: me }),
    "GET /api/crs/systems/": () => ({ body: [GRID, WGS, METRE] }),
    "GET /api/crs/defaults/": () => ({
      body: { system: GRID, district: null, user: null, effective: { crs: GRID, source: "system" } },
    }),
    "PUT /api/crs/defaults/me/": () => ({ status: 204 }),
    "GET /api/crs/operations/": () => ({
      body: {
        current: { name: "Accra to WGS 84 (4)", pipeline: "p4", accuracy_m: 6, pinned: false },
        candidates: [
          { name: "Accra to WGS 84 (4)", pipeline: "p4", accuracy_m: 6, pinned: false },
          { name: "Accra to WGS 84 (1)", pipeline: "p1", accuracy_m: 25, pinned: false },
        ],
      },
    }),
    "POST /api/crs/transform/": () => ({
      body: {
        points: [[1190631.4519, 337708.9446]],
        operation: { name: "Accra to WGS 84 (4)", pipeline: "p4", accuracy_m: 6, pinned: false },
      },
    }),
  });
}

describe("coordinate systems page", () => {
  it("states where the effective default comes from", async () => {
    renderApp(backend().fetch, { tokens: signedIn, route: "/crs" });
    expect(await screen.findByText(/New projects start in/)).toHaveTextContent("EPSG:2136");
    expect(screen.getByText(/New projects start in/)).toHaveTextContent("from the system default");
  });

  it("converts coordinates and states the accuracy of the datum shift", async () => {
    const api = backend();
    renderApp(api.fetch, { tokens: signedIn, route: "/crs" });
    const form = await screen.findByRole("form", { name: "Convert coordinates" });
    await userEvent.type(within(form).getByRole("textbox"), "-0.2 5.6");
    await userEvent.click(within(form).getByRole("button", { name: "Convert" }));
    const result = await screen.findByRole("region", { name: "Conversion result" });
    expect(result).toHaveTextContent("Accra to WGS 84 (4) (±6 m)");
    expect(result).toHaveTextContent("E 1190631.452 ft (GC), N 337708.945 ft (GC)");
    const call = api.calls.find((c) => c.path === "/api/crs/transform/");
    expect(call?.body).toEqual({ from_crs: "EPSG:4326", to_crs: "EPSG:2136", points: [[-0.2, 5.6]] });
  });

  it("points out unreadable lines instead of sending them", async () => {
    const api = backend();
    renderApp(api.fetch, { tokens: signedIn, route: "/crs" });
    const form = await screen.findByRole("form", { name: "Convert coordinates" });
    await userEvent.type(within(form).getByRole("textbox"), "-0.2 5.6{enter}oops");
    await userEvent.click(within(form).getByRole("button", { name: "Convert" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent("Can't read line 2");
    expect(api.calls.some((c) => c.path === "/api/crs/transform/")).toBe(false);
  });

  it("saves a personal default", async () => {
    const api = backend();
    renderApp(api.fetch, { tokens: signedIn, route: "/crs" });
    await userEvent.selectOptions(await screen.findByLabelText("Your personal default"), "3");
    const put = api.calls.find((c) => c.method === "PUT");
    expect(put).toMatchObject({ path: "/api/crs/defaults/me/", body: { crs: 3 } });
  });

  it("district admins can add systems and set the district default; viewers can't", async () => {
    const view = renderApp(backend().fetch, { tokens: signedIn, route: "/crs" });
    expect(await screen.findByRole("form", { name: "Add coordinate system" })).toBeInTheDocument();
    expect(screen.getByLabelText("District default")).toBeEnabled();
    expect(screen.getByLabelText("System default")).toBeDisabled();
    view.unmount();

    localStorage.setItem("spatial.district.1", "20"); // the district where Ama is a viewer
    renderApp(backend().fetch, { tokens: signedIn, route: "/crs" });
    await screen.findByText(/New projects start in/);
    expect(screen.queryByRole("form", { name: "Add coordinate system" })).not.toBeInTheDocument();
    expect(screen.getByLabelText("District default")).toBeDisabled();
  });

  it("only system administrators can pin a transformation", async () => {
    renderApp(backend().fetch, { tokens: signedIn, route: "/crs" });
    await screen.findByText("Accra to WGS 84 (1)");
    expect(screen.queryByRole("button", { name: "Use this" })).not.toBeInTheDocument();
  });
});
