import type { PermitApplication } from "@spatial/map-core";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { ringFrom } from "./PermitsPage";
import { fakeBackend, makeMe } from "../test/fakeBackend";
import { clock, registry, summary } from "../test/permits";
import { renderApp, signedIn } from "../test/render";

beforeEach(() => localStorage.clear());

const by_status = { received: 2, review: 0, reported: 0, granted: 0, deferred: 0, refused: 0, issued: 0, withdrawn: 0 };

function backend(extra: Parameters<typeof fakeBackend>[0] = {}) {
  const late = summary(1, { next_due: clock({ due_on: "2026-09-08", overdue: true }), check_counts: { pass: 3, fail: 2, warn: 1, unknown: 1 } });
  return fakeBackend({
    "GET /api/auth/me/": () => ({ body: makeMe() }),
    "GET /api/permits/registry/": () => ({ body: registry }),
    "GET /api/permits/applications/": () => ({ body: { results: [late, summary(2)], summary: { total: 2, open: 2, overdue: 1, by_status } } }),
    "GET /api/permits/fees/": () => ({ body: [] }),
    "GET /api/projects/5/layer-roles/": () => ({ body: { roles: [{ role: "parcels", layer: 8, config: { id_field: "parcel_id" }, suggested: null }] } }),
    "GET /api/layers/8/features/": () => ({ body: { type: "FeatureCollection", crs_code: "EPSG:2136", numberMatched: 1, numberReturned: 1, next_offset: null, features: [{ type: "Feature", id: 77, geometry: null, properties: { parcel_id: "P-001" }, meta: {} }] } }),
    ...extra,
  });
}

describe("permits page", () => {
  it("shows what is open and what has passed its deadline", async () => {
    renderApp(backend().fetch, { tokens: signedIn, route: "/projects/5/permits" });
    const late = (await screen.findByText("DA/DP/2026/0001")).closest("tr")!;
    expect(late).toHaveTextContent("Acknowledge receipt in writing: overdue since 2026-09-08");
    expect(late).toHaveTextContent("2 not met, 1 to look into");
    const fine = screen.getByText("DA/DP/2026/0002").closest("tr")!;
    expect(fine).toHaveTextContent("by 2026-10-18");
    expect(fine).toHaveTextContent("nothing against it");
    const facts = screen.getByLabelText("Summary");
    expect(facts).toHaveTextContent("Open2");
    expect(facts).toHaveTextContent("With a deadline passed1");
  });

  it("receives an application for a parcel on the map", async () => {
    const api = backend({ "POST /api/permits/applications/": () => ({ status: 201, body: { ...summary(3) } as PermitApplication }) });
    renderApp(api.fetch, { tokens: signedIn, route: "/projects/5/permits" });
    await userEvent.click(await screen.findByRole("button", { name: "Receive an application" }));
    const form = screen.getByRole("form", { name: "Receive an application" });
    await userEvent.type(within(form).getByLabelText("Applicant"), "Kofi Boateng");
    await userEvent.type(within(form).getByLabelText("Proposed use"), "Shop");
    await userEvent.type(within(form).getByLabelText("Storeys"), "1");
    await waitFor(() => expect(api.calls.some((c) => c.path.startsWith("/api/layers/8/features/"))).toBe(true));
    await userEvent.type(within(form).getByLabelText("Parcel id"), "P-001");
    await userEvent.click(within(form).getByRole("button", { name: "Receive the application" }));
    await waitFor(() => expect(api.calls.some((c) => c.method === "POST")).toBe(true));
    expect(api.calls.find((c) => c.method === "POST")!.body).toEqual({
      project: 5,
      kind: "development",
      category: "building",
      applicant_name: "Kofi Boateng",
      proposed_use: "Shop",
      proposed_floors: 1,
      site_feature: 77,
    });
  });

  it("offers only the categories of the chosen kind of permit, and refuses an unknown parcel", async () => {
    const api = backend();
    renderApp(api.fetch, { tokens: signedIn, route: "/projects/5/permits" });
    await userEvent.click(await screen.findByRole("button", { name: "Receive an application" }));
    const form = screen.getByRole("form", { name: "Receive an application" });
    expect(within(within(form).getByLabelText("For")).queryByRole("option", { name: "Change of use" })).not.toBeInTheDocument();
    await userEvent.selectOptions(within(form).getByLabelText("Permit"), "planning");
    expect(within(form).getByLabelText("For")).toHaveValue("change_of_use");
    await userEvent.type(within(form).getByLabelText("Applicant"), "Kofi");
    await userEvent.type(within(form).getByLabelText("Parcel id"), "P-999");
    await userEvent.click(within(form).getByRole("button", { name: "Receive the application" }));
    expect(await within(form).findByRole("alert")).toHaveTextContent('No parcel "P-999"');
    expect(api.calls.some((c) => c.method === "POST")).toBe(false);
  });

  it("turns typed corners into a closed plot", () => {
    expect(ringFrom("10, 20\n40 20\n40;50")).toEqual({ type: "Polygon", coordinates: [[[10, 20], [40, 20], [40, 50], [10, 20]]] });
    expect(ringFrom("10, 20\n40, 20")).toBe("Give at least three corners, one per line.");
    expect(ringFrom("10, 20\nnorth, 5\n1, 2")).toBe('"north, 5" isn\'t an easting and a northing.');
  });

  it("lets only the administrator enter the fee-fixing resolution", async () => {
    const planner = makeMe({ memberships: [{ district: { id: 10, name: "Sample Municipal Assembly", code: "SMA" }, role: "planner", permissions: ["district.view", "project.view", "permit.view", "permit.process", "permit.inspect"] }] });
    renderApp(backend({ "GET /api/auth/me/": () => ({ body: planner }) }).fetch, { tokens: signedIn, route: "/projects/5/permits" });
    expect(await screen.findByRole("button", { name: "Receive an application" })).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Fees" })).queryByRole("button", { name: "Add a fee" })).not.toBeInTheDocument();
  });
});
